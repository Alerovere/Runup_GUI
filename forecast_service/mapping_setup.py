"""One-off GeoTIFF preparation for lightweight static-map publication."""
from pathlib import Path
import json

import numpy as np

from forecast_service.inundation import png_bytes, load_grid, MAX_ORTHOPHOTO_CELLS
from forecast_service.sectors import valid_id, validate_mappings


class SeedSelectionError(ValueError):
    """Keep per-transect diagnostics available when no coastal cell is found."""
    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def select_sea_seeds(z, transform, *, seed_points=None, seed_profiles=None,
                     max_advance_m=5.0, max_rise_m=0.5):
    """Choose first valid prepared cell on the initial sea-to-land profile.

    Manual points are strict and never relocated. Automatic profiles map an ID
    to ordered [lon, lat, distance_from_first_valid_m, source_elevation_m]
    samples. Elevations must already use the map's vertical correction.
    Never search in 2-D or jump beyond a source terrain barrier to find a seed.
    """
    import math
    from pyproj import Transformer
    from rasterio.transform import rowcol, xy
    if seed_points is not None and seed_profiles is not None:
        raise ValueError('Usare punti manuali oppure profili per l’avvio automatico, non entrambi.')
    if not seed_points and not seed_profiles:
        raise ValueError('Indicare punti o profili di partenza verso mare.')
    if not all(isinstance(x,(int,float)) and math.isfinite(x) and x>=0 for x in (max_advance_m,max_rise_m)):
        raise ValueError('Distanza e rialzo massimi di avvio devono essere finiti e non negativi.')
    to_map=Transformer.from_crs(4326,3857,always_xy=True)
    to_wgs=Transformer.from_crs(3857,4326,always_xy=True)
    height,width=z.shape
    seeds=np.zeros(z.shape,dtype=bool)
    report=[]
    def cell(point):
        if len(point)!=2 or not np.isfinite(point).all() or not -180<=point[0]<=180 or not -85<point[1]<85:
            raise ValueError('Coordinate di avvio: servono longitudine e latitudine WGS84 valide.')
        x,y=to_map.transform(*point)
        row,col=rowcol(transform,x,y)
        if not 0<=row<height or not 0<=col<width or not np.isfinite(z[row,col]):
            return None
        return int(row),int(col)
    if seed_points is not None:
        for i,point in enumerate(seed_points,1):
            selected=cell(point)
            if selected is None:
                raise ValueError(f'Punto a mare manuale {i} fuori dalla griglia preparata o su NoData: scegliere una cella valida; coordinate {point}.')
            row,col=selected;seeds[row,col]=True
            report.append(dict(transect_id=f'manuale-{i}',status='manuale',advance_m=0.,
                               requested_point=list(point),selected_point=list(point),grid_elevation_m=float(z[row,col])))
        return seeds,report
    if not isinstance(seed_profiles,dict) or not seed_profiles:
        raise ValueError('Profili di avvio automatico non validi.')
    for identifier,samples in seed_profiles.items():
        samples=np.asarray(samples,dtype=float)
        if samples.ndim!=2 or samples.shape[1]!=4 or not len(samples) or not np.isfinite(samples).all():
            raise ValueError(f'Transetto {identifier}: campioni di avvio non validi.')
        if abs(samples[0,2])>1e-6 or (np.diff(samples[:,2])<0).any() or (samples[:,2]<0).any():
            raise ValueError(f'Transetto {identifier}: le distanze devono partire da zero e crescere verso terra.')
        reference=float(samples[0,3]);selected=None
        for lon,lat,distance,elevation in samples:
            # Strict prefix: a low cell beyond a crest is not a valid shortcut.
            if distance>max_advance_m+1e-8 or elevation>reference+max_rise_m+1e-8:
                break
            candidate=cell([lon,lat])
            if candidate is None:
                continue
            row,col=candidate
            if float(z[row,col])>reference+max_rise_m+1e-8:
                continue
            selected=(row,col,lon,lat,distance)
            break
        if selected is None:
            report.append(dict(transect_id=str(identifier),status='nessuna_cella_costiera_valida',advance_m=None,
                               requested_point=samples[0,:2].tolist(),selected_point=None,grid_elevation_m=None))
            continue
        row,col,lon,lat,distance=selected
        center=xy(transform,row,col)
        seeds[row,col]=True
        report.append(dict(transect_id=str(identifier),status='iniziale' if distance<1e-8 else 'avanzato_sul_transetto',
                           advance_m=float(distance),requested_point=samples[0,:2].tolist(),
                           selected_point=[float(lon),float(lat)],grid_cell_center=list(to_wgs.transform(*center)),
                           grid_elevation_m=float(z[row,col])))
    failed=[r['transect_id'] for r in report if r['selected_point'] is None]
    if failed:
        raise SeedSelectionError('Nessuna cella costiera valida per i transetti '+', '.join(failed)+
            f' entro {max_advance_m:g} m e {max_rise_m:g} m di rialzo. Controllare la diagnostica o PUNTI_MARE_MANUALI.',report)
    return seeds,report


def prepare_mapping(dem_path, output, *, slug, unit_id='whole', orthophoto_path=None,
                    display_polygon=None, seed_points=None, survey_credit='', survey_date='',
                    license='', vertical_reference='', dem_offset_m=0.0,
                    vertical_alignment_confirmed=False, max_dimension=768, clip_to_polygon=False, clip_buffer_m=100,
                    orthophoto_resolution_m=None, seed_profiles=None,
                    seed_max_advance_m=5.0, seed_max_rise_m=0.5):
    """Prepare a local map from a full-area DEM; preserve originals outside Git.

    Polygon and sea-side seed points use WGS84 lon/lat. Offset is ADDED once to
    DEM heights to match the TWL reference, independently of profile corrections.
    Full DEM extent is the connectivity domain, polygon is only a display mask.
    """
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds, transform_geom, transform as reproject_coordinates
    from rasterio.transform import from_bounds, rowcol
    from rasterio.features import geometry_mask
    if not valid_id(slug) or not valid_id(unit_id) or not isinstance(max_dimension, int) or not 32 <= max_dimension <= 1024:
        raise ValueError('Identificativi o dimensione della griglia non validi.')
    prefix = f'config/study_sites/{slug}/cartography/{unit_id}/'
    metadata = dict(grid_file=prefix+'grid.npz', orthophoto_file=prefix+'orthophoto.png' if orthophoto_path else None,
                    survey_credit=survey_credit, survey_date=survey_date, license=license, vertical_reference=vertical_reference,
                    dem_offset_m=float(dem_offset_m), vertical_alignment_confirmed=vertical_alignment_confirmed)
    validate_mappings({'mapping': metadata} if unit_id == 'whole' else {'sectors': {unit_id: {'mapping': metadata}}}, slug)
    if not seed_points and not seed_profiles:
        raise ValueError('Indicare punti di partenza verso mare in celle valide del DEM (lon, lat).')
    with rasterio.open(dem_path) as dem:
        if not dem.crs or dem.count != 1:
            raise ValueError('DEM: GeoTIFF con una banda, CRS e quote in metri richiesti.')
        if dem.units[0] not in (None, '', 'm', 'metre', 'meter', 'metres', 'meters'):
            raise ValueError('Convertire le quote del DEM in metri.')
        left, bottom, right, top = transform_bounds(dem.crs, 'EPSG:3857', *dem.bounds)
        native_transform, width, height = calculate_default_transform(dem.crs, 'EPSG:3857', dem.width, dem.height, *dem.bounds)
        if clip_to_polygon:
            if not display_polygon:
                raise ValueError('Poligono necessario per il clipping automatico.')
            from forecast_service.geospatial_setup import buffered_map_bounds
            crop = buffered_map_bounds(display_polygon, clip_buffer_m)
            left, bottom, right, top = max(left,crop[0]), max(bottom,crop[1]), min(right,crop[2]), min(top,crop[3])
            if left >= right or bottom >= top:
                raise ValueError('Il settore non interseca il DEM.')
            width = max(1, int(np.ceil((right-left)/abs(native_transform.a))))
            height = max(1, int(np.ceil((top-bottom)/abs(native_transform.e))))
        west, south, east, north = transform_bounds('EPSG:3857', 'EPSG:4326', left, bottom, right, top)
        if not -180 <= west < east <= 180 or not -90 <= south < north <= 90 or east-west > .2 or north-south > .2:
            raise ValueError('Area troppo grande: attivare clip_to_polygon o suddividere in settori più piccoli.')
        factor = min(1, max_dimension/max(width, height))
        width, height = max(1, round(width*factor)), max(1, round(height*factor))
        transform = from_bounds(left, bottom, right, top, width, height)
        z = np.full((height, width), np.nan, dtype=np.float32)
        # Never average away a seawall. Resolution limits still need field review.
        reproject(rasterio.band(dem, 1), z, src_transform=dem.transform, src_crs=dem.crs,
                  src_nodata=dem.nodata, dst_transform=transform, dst_crs='EPSG:3857', dst_nodata=np.nan,
                  resampling=Resampling.nearest)
        z = z*float(dem.scales[0])+float(dem.offsets[0])
        z += metadata['dem_offset_m']
    if not display_polygon or display_polygon.get('type') not in ('Polygon', 'MultiPolygon'):
        raise ValueError('Definire il poligono WGS84 dell’area da rappresentare.')
    display = geometry_mask([transform_geom("EPSG:4326", "EPSG:3857", display_polygon)], out_shape=z.shape, transform=transform, invert=True)
    seeds, seed_report = select_sea_seeds(z, transform, seed_points=seed_points, seed_profiles=seed_profiles,
                                        max_advance_m=seed_max_advance_m, max_rise_m=seed_max_rise_m)
    metadata['seed_selection'] = seed_report
    metadata['seed_selection_limits'] = dict(max_advance_m=seed_max_advance_m,max_rise_m=seed_max_rise_m)
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    grid = output/'grid.npz'
    np.savez_compressed(grid, z=z, seeds=seeds, display_mask=display, bounds=np.array([west, south, east, north]))
    load_grid(grid)
    assets = {f'cartography/{unit_id}/grid.npz': grid}
    if orthophoto_path:
        ortho_width, ortho_height = width, height
        ortho_transform = transform
        if orthophoto_resolution_m is not None:
            import math
            from pyproj import Geod
            if not isinstance(orthophoto_resolution_m, (int, float)) or not math.isfinite(orthophoto_resolution_m) or orthophoto_resolution_m <= 0:
                raise ValueError('Risoluzione ortofoto: indicare metri/pixel positivi.')
            geod = Geod(ellps='WGS84')
            ground_width = geod.inv(west, (south+north)/2, east, (south+north)/2)[2]
            ground_height = geod.inv((west+east)/2, south, (west+east)/2, north)[2]
            ortho_width = max(1, math.ceil(ground_width/orthophoto_resolution_m))
            ortho_height = max(1, math.ceil(ground_height/orthophoto_resolution_m))
            if max(ortho_width, ortho_height) > 4096 or ortho_width*ortho_height > MAX_ORTHOPHOTO_CELLS:
                raise ValueError('Ritaglio ortofoto oltre 4096 pixel per asse: aumentare il passo in metri/pixel o ridurre l’area.')
            ortho_transform = from_bounds(left, bottom, right, top, ortho_width, ortho_height)
            metadata['orthophoto_ground_resolution_m'] = [ground_width/ortho_width, ground_height/ortho_height]
        with rasterio.open(orthophoto_path) as ortho:
            if not ortho.crs or ortho.count not in (1, 3, 4) or any(dtype != 'uint8' for dtype in ortho.dtypes):
                raise ValueError('Ortofoto: GeoTIFF georeferenziato a 8 bit, grigio/RGB/RGBA.')
            rgba = np.zeros((ortho_height, ortho_width, 4), dtype=np.uint8)
            bands = [1, 1, 1] if ortho.count == 1 else [1, 2, 3]
            for channel, band in enumerate(bands):
                reproject(rasterio.band(ortho, band), rgba[:, :, channel], src_transform=ortho.transform,
                          src_crs=ortho.crs, dst_transform=ortho_transform, dst_crs='EPSG:3857', resampling=Resampling.bilinear)
            # Source mask honours alpha and NoData, without reading the whole mosaic.
            from rasterio.vrt import WarpedVRT
            from rasterio.enums import ColorInterp
            with WarpedVRT(ortho, crs='EPSG:3857', transform=ortho_transform, width=ortho_width, height=ortho_height,
                           add_alpha=ColorInterp.alpha not in ortho.colorinterp) as vrt:
                valid = vrt.dataset_mask()
            ortho_display = geometry_mask([transform_geom('EPSG:4326', 'EPSG:3857', display_polygon)],
                                          out_shape=(ortho_height, ortho_width), transform=ortho_transform, invert=True)
            rgba[:, :, 3] = np.where(ortho_display, valid, 0)
            raw = png_bytes(rgba, max_cells=MAX_ORTHOPHOTO_CELLS)
            if len(raw) > 12*1024*1024:
                raise ValueError('Ortofoto preparata oltre 12 MiB: aumentare il passo o ridurre il ritaglio.')
            image = output/'orthophoto.png'; image.write_bytes(raw)
            assets[f'cartography/{unit_id}/orthophoto.png'] = image
        metadata['orthophoto_shape'] = [ortho_height, ortho_width]
        metadata['orthophoto_target_resolution_m'] = orthophoto_resolution_m
    metadata['clip_to_polygon'] = bool(clip_to_polygon)
    metadata['clip_buffer_m'] = clip_buffer_m if clip_to_polygon else None
    metadata['prepared_crs'] = 'EPSG:3857'
    metadata['prepared_grid_shape'] = list(z.shape)
    metadata['dem_source_name'] = Path(dem_path).name
    metadata['orthophoto_source_name'] = Path(orthophoto_path).name if orthophoto_path else None
    metadata['processing_note'] = 'DEM ricampionato al vicino più prossimo; verificare opere strette e risoluzione. Connessione nel dominio locale con margine, ritaglio sul poligono solo in uscita.'
    (output/'mapping.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    return metadata, assets
