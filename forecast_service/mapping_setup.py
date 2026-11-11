"""One-off GeoTIFF preparation for lightweight static-map publication."""
from pathlib import Path
import json

import numpy as np

from forecast_service.inundation import png_bytes, load_grid, MAX_ORTHOPHOTO_CELLS
from forecast_service.sectors import valid_id, validate_mappings


def prepare_mapping(dem_path, output, *, slug, unit_id='whole', orthophoto_path=None,
                    display_polygon=None, seed_points=None, survey_credit='', survey_date='',
                    license='', vertical_reference='', dem_offset_m=0.0,
                    vertical_alignment_confirmed=False, max_dimension=768, clip_to_polygon=False, clip_buffer_m=100,
                    orthophoto_resolution_m=None):
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
    if not seed_points:
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
    seeds = np.zeros(z.shape, dtype=bool)
    for point in seed_points:
        if len(point) != 2 or not np.isfinite(point).all():
            raise ValueError('Coordinate dei punti a mare non valide.')
        xx, yy = reproject_coordinates("EPSG:4326", "EPSG:3857", [point[0]], [point[1]])
        row, col = rowcol(transform, xx[0], yy[0])
        if not 0 <= row < height or not 0 <= col < width or not np.isfinite(z[row, col]):
            raise ValueError('Un punto a mare è fuori dal DEM o su NoData: scegliere una cella valida.')
        seeds[row, col] = True
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
