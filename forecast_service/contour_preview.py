"""Display-only outer reach lines. Never fill cells or change terrain heights.

The connected wet mask remains the scientific/geometric result. This optional
setup preview omits internal island outlines and simplifies the external
wet/dry interface. It is not applied to published forecasts or impact metrics.
"""
import hashlib
import math
from pathlib import Path

import numpy as np

METHOD = 'external_reach_lines_display_only_v1'
MAX_CELLS = 1024 * 1024
MAX_SEGMENTS = 200000


def _boolean(value, shape, name):
    a = np.asarray(value)
    if a.dtype != bool or a.shape != shape:
        raise ValueError(f'{name}: serve una maschera booleana con le dimensioni della griglia.')
    return a


def _lines(geometry):
    from shapely.geometry import MultiLineString
    if geometry.is_empty:
        return MultiLineString([])
    if geometry.geom_type in ('LineString', 'MultiLineString'):
        return geometry
    result = []
    if hasattr(geometry, 'geoms'):
        for part in geometry.geoms:
            line = _lines(part)
            if line.geom_type == 'LineString' and not line.is_empty:
                result.append(line)
            elif line.geom_type == 'MultiLineString':
                result.extend(line.geoms)
    return MultiLineString(result)


def _vertices(geometry):
    if geometry.is_empty:
        return 0
    if geometry.geom_type == 'LineString':
        return len(geometry.coords)
    return sum(_vertices(part) for part in geometry.geoms)


def reach_lines(reached, valid, *, pixel_size_m=(1., 1.), display_mask=None, tolerance_m=1.):
    """Return original/simplified outer interfaces in local ground metres.

    x increases by column; y decreases by row, origin at the top-left corner.
    Dry components enclosed inside the reached area are not drawn. Interfaces
    against NoData, raster edges or an artificial display crop are not invented.
    Classification uses the whole grid before applying the display mask.
    """
    from scipy import ndimage
    from shapely.geometry import MultiLineString, shape, mapping
    from shapely import line_merge
    from shapely.ops import unary_union
    from affine import Affine
    from rasterio.features import shapes

    reached = np.asarray(reached)
    if reached.ndim != 2 or not reached.size or reached.size > MAX_CELLS or reached.dtype != bool:
        raise ValueError('Griglia di risalita non valida o oltre 1024 × 1024 celle.')
    valid = _boolean(valid, reached.shape, 'Copertura valida')
    display = np.ones(reached.shape, bool) if display_mask is None else _boolean(display_mask, reached.shape, 'Area da mostrare')
    if (reached & ~valid).any():
        raise ValueError('La risalita contiene celle senza dato altimetrico.')
    if len(pixel_size_m) != 2 or not np.isfinite(pixel_size_m).all() or min(pixel_size_m) <= 0:
        raise ValueError('Dimensioni delle celle in metri non valide.')
    if not isinstance(tolerance_m, (int, float)) or not math.isfinite(tolerance_m) or not 0 <= tolerance_m <= 20:
        raise ValueError('Tolleranza del contorno: scegliere un valore fra 0 e 20 metri.')
    dx, dy = map(float, pixel_size_m)
    dry = ~reached
    border = np.zeros(reached.shape, bool)
    border[0, :] = dry[0, :]; border[-1, :] = dry[-1, :]
    border[:, 0] = dry[:, 0]; border[:, -1] = dry[:, -1]
    external = ndimage.binary_propagation(border, structure=np.ones((3, 3), bool), mask=dry)
    segments = []
    # Vertical edges between left/right cells, with both cells observed.
    left_wet = reached[:, :-1] & external[:, 1:] & display[:, :-1]
    right_wet = reached[:, 1:] & external[:, :-1] & display[:, 1:]
    edges = (left_wet | right_wet) & valid[:, :-1] & valid[:, 1:]
    rr, cc = np.nonzero(edges)
    if len(rr) > MAX_SEGMENTS:
        raise ValueError('Contorno troppo frammentato: ridurre la risoluzione della griglia cartografica e riprovare.')
    segments.extend([((float((c+1)*dx), float(-r*dy)),
                      (float((c+1)*dx), float(-(r+1)*dy))) for r, c in zip(rr, cc)])
    # Horizontal edges between upper/lower cells.
    upper_wet = reached[:-1, :] & external[1:, :] & display[:-1, :]
    lower_wet = reached[1:, :] & external[:-1, :] & display[1:, :]
    edges = (upper_wet | lower_wet) & valid[:-1, :] & valid[1:, :]
    rr, cc = np.nonzero(edges)
    if len(segments)+len(rr) > MAX_SEGMENTS:
        raise ValueError('Contorno troppo frammentato: ridurre la risoluzione della griglia cartografica e riprovare.')
    segments.extend([((float(c*dx), float(-(r+1)*dy)),
                      (float((c+1)*dx), float(-(r+1)*dy))) for r, c in zip(rr, cc)])
    original = line_merge(MultiLineString(segments)) if segments else MultiLineString([])
    simplified = original.simplify(float(tolerance_m), preserve_topology=True) if tolerance_m else original
    # Do not draw simplified chords through NoData or outside the display area.
    domain = valid & display
    polygons = [shape(g) for g, v in shapes(domain.astype('uint8'), mask=domain,
                transform=Affine(dx, 0, 0, 0, -dy, 0)) if v == 1]
    domain_geometry = unary_union(polygons)
    original = _lines(original.intersection(domain_geometry))
    simplified = _lines(simplified.intersection(domain_geometry))
    _, islands = ndimage.label(dry & ~external, structure=np.ones((3, 3), bool))
    report = dict(method=METHOD, display_only=True, reached_cells=int(reached.sum()),
                  filled_cells=0, mask_modified=False, elevations_modified=False,
                  internal_components_not_drawn=int(islands), interface_segments=len(segments),
                  pixel_size_ground_m=[dx, dy], tolerance_m=float(tolerance_m),
                  original_vertices=_vertices(original), simplified_vertices=_vertices(simplified),
                  original_length_m=float(original.length), simplified_length_m=float(simplified.length),
                  empty=bool(original.is_empty),
                  interpretation='Solo limite cartografico: non ricostruisce terreno né propagazione dietro false barriere del DSM.')
    return original, simplified, report


def preview_from_grid(grid_path, *, level_m, tolerance_m=1., display_polygon=None):
    """Use the existing connected_mask unchanged, then prepare WGS84 lines."""
    from pyproj import Transformer, Geod
    from shapely import transform
    from shapely.geometry import mapping, shape
    from forecast_service.inundation import load_grid, connected_mask

    if not isinstance(level_m, (int, float)) or not math.isfinite(level_m):
        raise ValueError('Quota di prova non valida.')
    z, seeds, display, bounds = load_grid(grid_path)
    reached = connected_mask(z, seeds, float(level_m))
    (south, west), (north, east) = bounds
    height, width = z.shape
    ground = Geod(ellps='WGS84')
    dx = ground.inv(west, (south+north)/2, east, (south+north)/2)[2]/width
    dy = ground.inv((west+east)/2, south, (west+east)/2, north)[2]/height
    original, simplified, report = reach_lines(reached, np.isfinite(z), pixel_size_m=(dx, dy),
                                                display_mask=display, tolerance_m=tolerance_m)
    to_merc = Transformer.from_crs(4326, 3857, always_xy=True)
    to_wgs = Transformer.from_crs(3857, 4326, always_xy=True)
    left, bottom = to_merc.transform(west, south); right, top = to_merc.transform(east, north)
    sx, sy = (right-left)/(width*dx), (top-bottom)/(height*dy)
    clip = None
    if display_polygon is not None:
        clip = transform(shape(display_polygon), lambda xy: np.column_stack(to_merc.transform(xy[:, 0], xy[:, 1])))
    def geographic(geometry):
        merc = transform(geometry, lambda xy: np.column_stack((left+xy[:, 0]*sx, top+xy[:, 1]*sy)))
        if clip is not None:
            merc = _lines(merc.intersection(clip))
        geo = transform(merc, lambda xy: np.column_stack(to_wgs.transform(xy[:, 0], xy[:, 1])))
        return dict(type='FeatureCollection', features=[] if geo.is_empty else [dict(type='Feature',
                    properties=dict(display_only=True, level_m=float(level_m)), geometry=mapping(geo))])
    report.update(level_m=float(level_m), grid_sha256=hashlib.sha256(Path(grid_path).read_bytes()).hexdigest(),
                  bounds_wgs84=bounds, bounds_3857=[left, bottom, right, top],
                  seeds_below_level=int((seeds & (z < level_m)).sum()))
    return geographic(original), geographic(simplified), report
