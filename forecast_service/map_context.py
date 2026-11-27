"""Display-only geographical context from prepared grids and surveyed points."""
import csv
import json
import math
from pathlib import Path

import numpy as np


def context_geometry(display,valid,bounds):
    from forecast_service.inundation_geojson import area_geometry
    from forecast_service.geospatial_setup import reproject_geometry
    from shapely.geometry import shape,mapping
    mask=display & valid
    geometry=area_geometry(mask,bounds)
    if not geometry:return {}
    polygon=reproject_geometry(shape(geometry),4326,3857).simplify(3,preserve_topology=True)
    geographic=reproject_geometry(polygon,3857,4326)
    west,south,east,north=geographic.bounds
    return dict(sector_geometry=mapping(geographic),display_bounds=[[south,west],[north,east]],
                geometry_note='Limite indicativo ricavato dal ritaglio del rilievo, semplificato a 3 m; solo per la visualizzazione.')


def surveyed_points(unit,root,slug,unit_id):
    """Use validated point metadata; support already exported legacy site packages."""
    points=[]
    for threshold in unit.get('thresholds',[]):
        for point in (threshold.get('survey_statistics') or {}).get('points',[]):
            if all(isinstance(point.get(k),(int,float)) and math.isfinite(point[k]) for k in ('latitude','longitude','elevation_m')):
                points.append(dict(point,threshold_id=threshold['id'],label=threshold.get('short_label') or threshold.get('description',threshold['id'])))
    if points:return points[:1000]
    directory=Path(root)/'config/study_sites'/slug/'diagnostics'
    geo=directory/'strutture.geojson';report=directory/'quote_strutture_punti.csv'
    if not geo.is_file() or not report.is_file():return []
    try:
        from pyproj import Transformer
        data=json.loads(geo.read_text());features=data.get('features',[])
        if len(features)>100000:return []
        crs=data.get('crs',{}).get('properties',{}).get('name','EPSG:4326')
        transform=Transformer.from_crs(crs,4326,always_xy=True)
        labels={str((t.get('survey_statistics') or {}).get('original_structure',t.get('short_label',''))).casefold():t for t in unit.get('thresholds',[])}
        with report.open() as stream:
            for row in csv.DictReader(stream):
                if row.get('status')!='valid' or row.get('sector_id')!=unit_id:continue
                t=labels.get(row.get('structure','').casefold())
                if not t:continue
                feature=features[int(row['point_index'])-1];g=feature.get('geometry') or {}
                if g.get('type')!='Point':continue
                lon,lat=transform.transform(*g['coordinates'][:2]);height=float(row['elevation_m'])
                if not all(math.isfinite(v) for v in (lon,lat,height)) or not -180<=lon<=180 or not -90<=lat<=90:continue
                points.append(dict(longitude=lon,latitude=lat,elevation_m=height,threshold_id=t['id'],label=t.get('short_label',t['description'])))
        return points[:1000]
    except (ValueError,KeyError,IndexError,TypeError,OSError):return []
