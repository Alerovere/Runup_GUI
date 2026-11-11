"""Propose exposed-structure elevations from original DEM cells at mapped points.

    Each valid point has equal weight. Means group by coastal sector and the
    normalized 'struttura' label, not by all DEM cells in a sector. Geometry Z
    never supplies a height. Keep every invalid observation in the audit table.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata


def structure_label(value):
    if not isinstance(value, str):
        raise ValueError('Il campo struttura deve contenere un nome testuale.')
    label = ' '.join(unicodedata.normalize('NFKC', value).split())
    if not label:
        raise ValueError('Nome struttura mancante.')
    return label, label.casefold()


def thresholds_from_structure_points(dem_path, points_path, coastal_polygons, *,
                                    geojson_crs='EPSG:4326', label_field='struttura',
                                    elevation_correction_m=0., sector_field='settore_costiero', season_field='stagione'):
    import numpy as np
    import pandas as pd
    import rasterio
    from pyproj import CRS
    from shapely.geometry import shape
    from shapely.errors import ShapelyError
    from forecast_service.geospatial_setup import reproject_geometry
    if not coastal_polygons or not math.isfinite(elevation_correction_m):
        raise ValueError('Settori costieri o correzione delle quote non validi.')
    polygons = {key: shape(value) for key, value in coastal_polygons.items()}
    if any(poly.geom_type not in ('Polygon', 'MultiPolygon') or poly.is_empty or not poly.is_valid for poly in polygons.values()):
        raise ValueError('Poligoni dei settori costieri non validi.')
    raw = Path(points_path).read_bytes()
    data = json.loads(raw)
    if data.get('type') != 'FeatureCollection' or not data.get('features') or len(data['features']) > 100000:
        raise ValueError('Serve un GeoJSON FeatureCollection di punti non vuoto (massimo 100.000 punti).')
    source_crs = CRS.from_user_input(geojson_crs)
    declared = data.get('crs', {}).get('properties', {}).get('name')
    if declared and not source_crs.equals(CRS.from_user_input(declared), ignore_axis_order=True):
        raise ValueError('Il CRS dichiarato nei punti differisce dal CRS indicato nel notebook.')
    observations = []
    season_names = {'summer':'summer', 'estiva':'summer', 'all_year':'all_year', 'annuale':'all_year'}
    with rasterio.open(dem_path) as dem:
        if dem.count != 1 or not dem.crs or dem.units[0] not in (None, '', 'm', 'metre', 'meter', 'metres', 'meters'):
            raise ValueError('DEM delle strutture: una banda, CRS e quote in metri richiesti.')
        scale, offset = float(dem.scales[0]), float(dem.offsets[0])
        if not all(math.isfinite(v) for v in (scale, offset)):
            raise ValueError('Scala o offset del DEM non validi.')
        for index, feature in enumerate(data['features'], 1):
            if not isinstance(feature, dict):
                feature = {}
            properties = feature.get('properties') or {}
            if not isinstance(properties, dict):
                properties = {}
            row = dict(point_index=index, feature_id=feature.get('id', properties.get('id', index)),
                       structure=None, structure_key=None, sector_id=None, elevation_m=None,
                       dem_elevation_m=None, dem_row=None, dem_col=None,
                       season=None, season_assumed=False, status='invalid_geometry', reason='Serve una geometria Point valida.')
            try:
                label, normalized = structure_label(properties.get(label_field))
                row.update(structure=label, structure_key=normalized)
            except ValueError as error:
                row.update(status='missing_label', reason=str(error)); observations.append(row); continue
            try:
                if not isinstance(feature.get('geometry'), dict):
                    observations.append(row); continue
                point = shape(feature['geometry'])
                if point.geom_type != 'Point' or point.is_empty or not point.is_valid:
                    observations.append(row); continue
                point = reproject_geometry(point, source_crs, 'EPSG:4326')
                if not all(math.isfinite(v) for v in (point.x, point.y)):
                    observations.append(row); continue
            except (ValueError, TypeError, KeyError, ShapelyError):
                observations.append(row); continue
            candidates = [key for key, poly in polygons.items() if poly.covers(point)]
            explicit = properties.get(sector_field)
            if explicit is not None and str(explicit).strip():
                chosen = str(explicit)
                if chosen not in candidates:
                    row.update(status='invalid_sector', reason='Il settore_costiero dichiarato non contiene il punto.')
                    observations.append(row); continue
            elif len(candidates) != 1:
                row.update(status='outside_sectors' if not candidates else 'ambiguous_sector', reason=f'Il punto appartiene a {len(candidates)} settori costieri.')
                observations.append(row); continue
            else:
                chosen = candidates[0]
            row['sector_id'] = chosen
            native = reproject_geometry(point, 'EPSG:4326', dem.crs)
            r, c = dem.index(native.x, native.y)
            row.update(dem_row=r, dem_col=c)
            if not 0 <= r < dem.height or not 0 <= c < dem.width:
                row.update(status='outside_dem', reason='Punto fuori dall’estensione del DEM.')
                observations.append(row); continue
            sample = next(dem.sample([(native.x, native.y)], indexes=1, masked=True))
            if bool(np.ma.getmaskarray(sample)[0]) or not np.isfinite(sample[0]):
                row.update(status='nodata', reason='Quota DEM mancante; nessuno zero o riempimento automatico.')
                observations.append(row); continue
            value = float(sample[0])*scale+offset
            if not math.isfinite(value+float(elevation_correction_m)):
                row.update(status='invalid_elevation', reason='Quota trasformata non finita.')
                observations.append(row); continue
            row.update(dem_elevation_m=value, elevation_m=value+float(elevation_correction_m))
            season = properties.get(season_field)
            if season is None or season == '':
                row.update(season='all_year', season_assumed=True)
            elif not isinstance(season, str) or season.casefold().strip() not in season_names:
                row.update(status='invalid_season', reason='Stagione non valida: usare estiva/summer oppure annuale/all_year.')
                observations.append(row); continue
            else:
                row['season'] = season_names[season.casefold().strip()]
            row.update(status='valid', reason=''); observations.append(row)
        dem_crs = dem.crs.to_string()
    report = pd.DataFrame(observations)
    proposals = {key: [] for key in coastal_polygons}
    summaries = []
    grouped = report[report.sector_id.notna() & report.structure_key.notna()].groupby(['sector_id', 'structure_key'], sort=True)
    for (unit, key), group in grouped:
        valid = group[group.status == 'valid']
        seasons = set(valid.season)
        if len(seasons) > 1:
            raise ValueError(f'Stagioni discordanti per {group.structure.iloc[0]} nel settore {unit}: correggere i punti.')
        label = group.structure.iloc[0]
        mean = float(valid.elevation_m.mean()) if len(valid) else None
        stats = dict(method='arithmetic_mean_dem_points_v1', original_structure=label,
                     mean_elevation_m=mean, min_elevation_m=float(valid.elevation_m.min()) if len(valid) else None,
                     max_elevation_m=float(valid.elevation_m.max()) if len(valid) else None,
                     n_valid=int(len(valid)), n_excluded=int(len(group)-len(valid)),
                     n_dem_cells=int(len(valid[['dem_row', 'dem_col']].drop_duplicates())),
                     season_assumed=bool(valid.season_assumed.any()), elevation_correction_m=float(elevation_correction_m))
        summaries.append(dict(sector_id=unit, structure=label, **stats))
        if mean is not None:
            slug = re.sub('[^a-z0-9]+', '-', unicodedata.normalize('NFKD', key).encode('ascii', 'ignore').decode()).strip('-')[:35] or 'struttura'
            identifier = slug+'-'+hashlib.sha256(key.encode()).hexdigest()[:8]
            proposals[unit].append(dict(id=identifier, short_label=label, description='Possibile interessamento: '+label.lower(),
                                        elevation_m=mean, season=next(iter(seasons)), survey_statistics=stats))
    for values in proposals.values():
        values.sort(key=lambda item: (item['elevation_m'], item['id']))
    metadata = dict(method='arithmetic_mean_dem_points_v1', points_source_name=Path(points_path).name,
                    points_sha256=hashlib.sha256(raw).hexdigest(), geojson_crs=source_crs.to_string(), label_field=label_field,
                    dem_source_name=Path(dem_path).name, dem_crs=dem_crs,
                    dem_scale=scale, dem_offset=offset, elevation_correction_m=float(elevation_correction_m),
                    polygons_sha256=hashlib.sha256(json.dumps(coastal_polygons, sort_keys=True).encode()).hexdigest(),
                    n_points=len(report), n_valid=int((report.status == 'valid').sum()), n_excluded=int((report.status != 'valid').sum()))
    columns = ['sector_id', 'structure', 'method', 'original_structure', 'mean_elevation_m',
               'min_elevation_m', 'max_elevation_m', 'n_valid', 'n_excluded', 'n_dem_cells',
               'season_assumed', 'elevation_correction_m']
    return proposals, report, pd.DataFrame(summaries, columns=columns), metadata
