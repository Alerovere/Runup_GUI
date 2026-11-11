"""One-off profiles from DEM + GeoJSON; the beach-face fit remains unchanged."""
import hashlib
import json
import math
from pathlib import Path


def reproject_geometry(geometry, source_crs, target_crs):
    import numpy as np
    from pyproj import Transformer
    from shapely import transform
    converter = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(geometry, lambda xy: np.column_stack(converter.transform(xy[:, 0], xy[:, 1])))


def read_geojson(path, *, crs='EPSG:4326', target_crs='EPSG:32632', id_field='TR_ID', polygon=False, name_field='name'):
    from pyproj import CRS
    from shapely.geometry import shape
    from shapely import line_merge
    data = json.loads(Path(path).read_text())
    if data.get('type') != 'FeatureCollection' or not data.get('features'):
        raise ValueError('Serve un GeoJSON FeatureCollection non vuoto.')
    source_crs = CRS.from_user_input(crs)
    declared = data.get('crs', {}).get('properties', {}).get('name')
    if declared and not source_crs.equals(CRS.from_user_input(declared), ignore_axis_order=True):
        raise ValueError('Il CRS dichiarato nel GeoJSON differisce dal CRS indicato nel notebook.')
    results = {}
    for feature in data['features']:
        properties = feature.get('properties') or {}
        identifier = properties.get(id_field)
        if identifier is None or str(identifier).strip() == '':
            raise ValueError(f'Identificativo assente: verificare il campo {id_field}.')
        identifier = str(identifier)
        if identifier in results:
            raise ValueError(f'Identificativo GeoJSON duplicato: {identifier}.')
        geometry = shape(feature['geometry'])
        geometry = reproject_geometry(geometry, source_crs, target_crs)
        if not polygon and geometry.geom_type == 'MultiLineString':
            geometry = line_merge(geometry)
        expected = ('Polygon', 'MultiPolygon') if polygon else ('LineString',)
        if geometry.geom_type not in expected or geometry.is_empty or not geometry.is_valid or not all(math.isfinite(v) for v in geometry.bounds):
            raise ValueError(f'Geometria non valida per {identifier}: servono poligoni validi o linee continue.')
        results[identifier] = dict(geometry=geometry, name=str(properties.get(name_field) or identifier))
    return results


def extract_dem_profiles(dem_path, transects_path, *, profile_crs='EPSG:32632', geojson_crs='EPSG:4326', id_field='TR_ID', step_m=None):
    """Sample original DEM cells, including NoData as NaN; never interpolate holes.

    Distance follows the line for ordering only. The existing fitting function
    subsequently recomputes straight-line distance from the seaward first point.
    GeoJSON Z is deliberately ignored: all heights come from the DEM.
    """
    import numpy as np
    import pandas as pd
    import rasterio
    from pyproj import CRS, Transformer
    metric_crs = CRS.from_user_input(profile_crs)
    if not metric_crs.is_projected or not all(abs(axis.unit_conversion_factor-1) < 1e-9 for axis in metric_crs.axis_info[:2]):
        raise ValueError('Il CRS dei profili deve essere proiettato in metri.')
    lines = read_geojson(transects_path, crs=geojson_crs, target_crs=metric_crs, id_field=id_field)
    records, diagnostics = [], []
    with rasterio.open(dem_path) as dem:
        if dem.count != 1 or not dem.crs or dem.units[0] not in (None, '', 'm', 'metre', 'meter', 'metres', 'meters'):
            raise ValueError('DEM: una banda, CRS e quote in metri richiesti.')
        to_metric = Transformer.from_crs(dem.crs, metric_crs, always_xy=True)
        to_dem = Transformer.from_crs(metric_crs, dem.crs, always_xy=True)
        center = (dem.width/2, dem.height/2)
        pixel = [to_metric.transform(*(dem.transform*p)) for p in (center, (center[0]+1, center[1]), (center[0], center[1]+1))]
        native_step = min(math.dist(pixel[0], point) for point in pixel[1:])
        spacing = native_step if step_m is None or step_m == 0 else float(step_m)
        if not math.isfinite(spacing) or spacing <= 0:
            raise ValueError('Passo di campionamento non valido.')
        scale, offset = float(dem.scales[0]), float(dem.offsets[0])
        if not math.isfinite(scale) or not math.isfinite(offset):
            raise ValueError('Scala o offset del DEM non validi.')
        for identifier, item in lines.items():
            line = item['geometry']
            if not math.isfinite(line.length) or line.length <= 0:
                raise ValueError(f'Transetto {identifier} di lunghezza nulla.')
            count = math.ceil(line.length/spacing)+1
            if count > 100000 or len(records)+count > 1000000:
                raise ValueError('Troppi campioni: aumentare il passo o ridurre l’area.')
            distances = np.append(np.arange(0, line.length, spacing), line.length)
            points = [line.interpolate(float(distance)) for distance in distances]
            xy = [(point.x, point.y) for point in points]
            native_xy = [to_dem.transform(*point) for point in xy]
            missing, outside = 0, 0
            for distance, point, sample_xy, sample in zip(distances, xy, native_xy, dem.sample(native_xy, indexes=1, masked=True)):
                row, col = dem.index(*sample_xy)
                is_outside = not 0 <= row < dem.height or not 0 <= col < dem.width
                invalid = is_outside or bool(np.ma.getmaskarray(sample)[0]) or not np.isfinite(sample[0])
                value = float('nan') if invalid else float(sample[0])*scale+offset
                missing += int(invalid); outside += int(is_outside)
                records.append(dict(TR_ID=identifier, distance=float(distance), SAMPLE_1=value, X=point[0], Y=point[1]))
            chord = math.dist(xy[0], xy[-1])
            diagnostics.append(dict(transect_id=identifier, length_m=float(line.length), n_points=len(distances),
                                    missing_z=missing, outside_dem=outside, step_m=spacing,
                                    curved_profile=chord == 0 or line.length > chord*1.01))
        metadata = dict(method='dem_native_cell_sample_v1', dem_source_name=Path(dem_path).name,
                        transects_source_name=Path(transects_path).name, profile_crs=metric_crs.to_string(),
                        geojson_crs=CRS.from_user_input(geojson_crs).to_string(), dem_crs=dem.crs.to_string(), step_m=spacing,
                        dem_scale=scale, dem_offset=offset,
                        transects_sha256=hashlib.sha256(Path(transects_path).read_bytes()).hexdigest())
    return pd.DataFrame(records), pd.DataFrame(diagnostics), metadata


def sectors_from_beachfaces(areas_path, profiles, selections, included_ids, *, profile_crs='EPSG:32632',
                           geojson_crs='EPSG:4326', id_field='sector_id', name_field='name',
                           x_col='X', y_col='Y', manual=None):
    """Assign using the midpoint of the fitted beach face, not the inland line end.

    Boundaries, overlapping areas and unmatched points require an explicit
    decision. Do not clip profiles: removing their crest would change the fit.
    """
    from shapely.geometry import LineString, mapping
    from pyproj import Transformer
    from forecast_service.sectors import valid_id
    areas = read_geojson(areas_path, crs=geojson_crs, target_crs=profile_crs, id_field=id_field, polygon=True, name_field=name_field)
    if any(not valid_id(key) or key == 'whole' for key in areas):
        raise ValueError('Gli ID dei settori devono usare minuscole, numeri e trattini; whole è riservato.')
    included = [str(key) for key in included_ids]
    manual = manual or {}
    if set(manual)-set(included):
        raise ValueError('Assegnazioni manuali per transetti non inclusi.')
    sectors = {key: {'name': item['name'], 'transect_ids': []} for key, item in areas.items()}
    report = []
    for key in included:
        selected = profiles[key].loc[selections[key], [x_col, y_col]]
        beachface = LineString(selected.to_numpy())
        point = beachface.interpolate(.5, normalized=True)
        candidates = [identifier for identifier, item in areas.items() if item['geometry'].covers(point)]
        chosen = manual.get(key)
        if chosen is not None:
            if chosen not in areas or not areas[chosen]['geometry'].intersects(beachface):
                raise ValueError(f'Assegnazione manuale non coerente con la battigia del transetto {key}.')
        elif len(candidates) != 1:
            raise ValueError(f'Transetto {key}: punto centrale della battigia in {len(candidates)} settori. Correggere i poligoni o indicare ASSEGNAZIONI_MANUALI.')
        else:
            chosen = candidates[0]
        sectors[chosen]['transect_ids'].append(key)
        report.append(dict(transect_id=key, sector_id=chosen, method='manual' if key in manual else 'beachface_midpoint'))
    empty = [key for key, item in sectors.items() if not item['transect_ids']]
    if empty:
        raise ValueError('Settori senza transetti validi: '+', '.join(empty))
    polygons = {key: mapping(reproject_geometry(item['geometry'], profile_crs, 'EPSG:4326')) for key, item in areas.items()}
    import pandas as pd
    return sectors, polygons, pd.DataFrame(report)


def buffered_map_bounds(polygon, buffer_m):
    """A local calculation domain in Web Mercator, with a ground-metre buffer."""
    from shapely.geometry import shape
    from pyproj import Transformer
    if not isinstance(buffer_m, (int, float)) or not math.isfinite(buffer_m) or not 10 <= buffer_m <= 2000:
        raise ValueError('Margine di clipping: scegliere da 10 a 2000 metri.')
    geometry = shape(polygon)
    if geometry.geom_type not in ('Polygon', 'MultiPolygon') or geometry.is_empty or not geometry.is_valid:
        raise ValueError('Poligono di clipping non valido.')
    center = geometry.centroid
    if not -180 <= center.x <= 180 or not 0 <= center.y <= 84:
        raise ValueError('Poligono WGS84 fuori dal dominio previsto per il setup mediterraneo.')
    zone = min(60, int((center.x+180)//6)+1)
    local_crs = f'EPSG:{32600+zone}'
    local = reproject_geometry(geometry, 'EPSG:4326', local_crs).buffer(buffer_m)
    return reproject_geometry(local, local_crs, 'EPSG:3857').bounds
