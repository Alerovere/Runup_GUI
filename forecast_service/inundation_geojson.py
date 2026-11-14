"""Timestamped GIS exports of the same static reach masks used by the PNGs."""
import json
import math

import numpy as np

MAX_GEOJSON_BYTES = 25 * 1024 * 1024


def _coordinates(shape,bounds):
    from pyproj import Transformer,Geod
    from rasterio.transform import from_bounds
    (south,west),(north,east)=bounds
    height,width=shape
    to_map=Transformer.from_crs(4326,3857,always_xy=True)
    left,bottom=to_map.transform(west,south);right,top=to_map.transform(east,north)
    geod=Geod(ellps='WGS84')
    dx=geod.inv(west,(south+north)/2,east,(south+north)/2)[2]/width
    dy=geod.inv((west+east)/2,south,(west+east)/2,north)[2]/height
    return from_bounds(left,bottom,right,top,width,height),(left,bottom,right,top), (dx,dy)


def area_geometry(mask,bounds):
    """Exact prepared-cell footprint, including holes and separate components."""
    from rasterio.features import shapes
    from rasterio.warp import transform_geom
    from shapely.geometry import shape,mapping
    from shapely.geometry.polygon import orient
    from shapely import make_valid
    transform,_,_=_coordinates(mask.shape,bounds)
    polygons=[]
    def parts(g):
        if g.geom_type=='Polygon':return [g]
        return [p for child in getattr(g,'geoms',[]) for p in parts(child)]
    for geometry,value in shapes(mask.astype('uint8'),mask=mask,transform=transform,connectivity=4):
        if value==1:
            polygon=shape(geometry)
            if not polygon.is_valid:polygon=make_valid(polygon)
            for part in parts(polygon):
                geographic=transform_geom('EPSG:3857','EPSG:4326',mapping(orient(part,sign=1.)))
                polygons.append(geographic['coordinates'])
    return dict(type='MultiPolygon',coordinates=polygons) if polygons else None


def limit_geometry(reached,valid,display,bounds,tolerance_m):
    """Display-only external front: same algorithm as the Colab line preview."""
    from shapely import transform
    from shapely.geometry import mapping
    from pyproj import Transformer
    from forecast_service.contour_preview import reach_lines
    _,(left,bottom,right,top),(dx,dy)=_coordinates(reached.shape,bounds)
    _,simplified,report=reach_lines(reached,valid,pixel_size_m=(dx,dy),display_mask=display,tolerance_m=tolerance_m)
    height,width=reached.shape
    sx,sy=(right-left)/(width*dx),(top-bottom)/(height*dy)
    to_wgs=Transformer.from_crs(3857,4326,always_xy=True)
    merc=transform(simplified,lambda xy:np.column_stack([left+xy[:,0]*sx,top+xy[:,1]*sy]))
    geographic=transform(merc,lambda xy:np.column_stack(to_wgs.transform(xy[:,0],xy[:,1])))
    return (mapping(geographic) if not geographic.is_empty else None),report


def export_geojson(masks,*,valid,display,bounds,metadata,unit,slug,unit_id,tolerance_m=3.):
    """Return separate area/line collections for the mean and central upper end.

    An empty mask/front is a null geometry, explicitly marked, never an invented
    boundary at NoData or the grid edge. Source masks and heights are read-only.
    """
    from forecast_service.ensemble import STATISTICS_METHOD
    if isinstance(tolerance_m,bool) or not isinstance(tolerance_m,(int,float)) or not math.isfinite(tolerance_m) or not 0<=tolerance_m<=20:
        raise ValueError('Tolleranza GeoJSON: scegliere un valore fra 0 e 20 m.')
    common=dict(location_id=slug,sector_id=unit_id,unit_name=unit.get('name',slug),
        issued_at_utc=metadata['issued_at_utc'],generated_at_utc=metadata['generated_at_utc'],
        forecast_from_utc=metadata['period_from'],forecast_to_utc=metadata['period_to'],period_end_exclusive=True,
        data_mode=metadata['data_mode'],method=metadata['method'],statistics_method=STATISTICS_METHOD,grid_sha256=metadata['grid_sha256'],
        vertical_reference=metadata['vertical_reference'],dem_offset_m=metadata['dem_offset_m'],
        survey_credit=metadata['survey_credit'],survey_date=metadata['survey_date'],license=metadata['license'],
        hours_non_frontal=metadata['hours_non_frontal'],hours_direction_unknown=metadata['hours_direction_unknown'],
        interpretation=metadata['interpretation'])
    area_features=[];line_features=[]
    for layer,reached in masks:
        mask=reached & display
        properties=dict(common,estimate=layer['kind'],estimate_label=layer['label'],statistic=layer['statistic'],
            percentile=layer['percentile'],twl_level_m=layer['level_m'],peak_time_utc=layer['peak_time'],
            seed_condition=layer['seed_condition'],quality_note=layer['quality_note'],
            peak_to_utc=layer['peak_to'],peak_windows_utc=layer['peak_windows'],cells=layer['cells'])
        area=area_geometry(mask,bounds)
        line,report=limit_geometry(reached,valid,display,bounds,float(tolerance_m))
        area_features.append(dict(type='Feature',properties=dict(properties,geometry_role='potential_area',
            simplified=False,empty=area is None),geometry=area))
        line_features.append(dict(type='Feature',properties=dict(properties,geometry_role='external_limit',
            display_only=True,tolerance_m=float(tolerance_m),empty=line is None,
            original_vertices=report['original_vertices'],simplified_vertices=report['simplified_vertices']),geometry=line))
    (south,west),(north,east)=bounds
    result={}
    for kind,features in [('aree',area_features),('limiti',line_features)]:
        collection=dict(type='FeatureCollection',bbox=[west,south,east,north],features=features)
        raw=(json.dumps(collection,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()
        if len(raw)>MAX_GEOJSON_BYTES:raise ValueError('GeoJSON oltre 25 MiB: controllare la frammentazione della griglia.')
        result[kind]=raw
    return result
