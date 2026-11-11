"""Small, explicitly synthetic inputs to exercise the same study-area workflow."""
from pathlib import Path
import json


def create_demo_survey(output, latitude, longitude, profile_crs):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from pyproj import Transformer
    from forecast_service.geospatial_setup import reproject_geometry
    from shapely.geometry import LineString, mapping
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    to_metric = Transformer.from_crs(4326, profile_crs, always_xy=True)
    x0, y0 = to_metric.transform(longitude, latitude)
    width, height = 90, 40
    x0, y0 = round(x0), round(y0)
    distance = np.arange(width)*1.
    z = np.empty((height, width), dtype=np.float32)
    for row in range(height):
        z[row] = (.045 if row < height/2 else .065)*distance-.3
        z[row, (distance >= 40) & (distance <= 56)] = .4
    transform = from_origin(x0, y0, 1, 1)
    dem = output/'dem_DEMO.tif'
    with rasterio.open(dem, 'w', driver='GTiff', height=height, width=width, count=1, dtype='float32', crs=profile_crs, transform=transform) as dst:
        dst.write(z, 1)
    ortho = output/'ortofoto_DEMO.tif'
    with rasterio.open(ortho, 'w', driver='GTiff', height=height, width=width, count=3, dtype='uint8', crs=profile_crs, transform=transform) as dst:
        dst.write(np.full((3, height, width), 175, dtype=np.uint8))
    features = []
    for identifier, row, reverse in [('T1', 10, False), ('T2', 30, True)]:
        xy = [(x0+.5, y0-row-.5), (x0+width-.5, y0-row-.5)]
        line = LineString(xy[::-1] if reverse else xy)
        features.append(dict(type='Feature', properties={'TR_ID': identifier}, geometry=mapping(reproject_geometry(line, profile_crs, 'EPSG:4326'))))
    lines = output/'transetti_DEMO.geojson'
    lines.write_text(json.dumps(dict(type='FeatureCollection', features=features)))
    return dem, ortho, lines
