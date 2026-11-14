"""Static, sea-connected potential reach. Not hydrodynamics or flood depth.

Prepared grids are bounded, north-up EPSG:3857 rasters (bounds in WGS84). Flood the full grid
before clipping to the display polygon; sector edges are not artificial walls.
The one-off raster preparation lives separately to keep production lightweight.
"""
from collections import deque
import hashlib
import math
from pathlib import Path
import struct
import zipfile
import zlib

import numpy as np

MAX_CELLS = 1024 * 1024
MAX_ORTHOPHOTO_CELLS = 4096 * 4096
METHOD = 'connected_static_twl_filtered_p75_p95_v1'


def png_bytes(rgba, *, max_cells=MAX_CELLS):
    rgba = np.asarray(rgba, dtype=np.uint8)
    height, width, channels = rgba.shape
    if channels != 4 or height * width > max_cells:
        raise ValueError('Dimensioni PNG non valide.')
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data) & 0xffffffff)
    pixels = b''.join(b'\0'+row.tobytes() for row in rgba)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')


def orthophoto_bytes(path, grid_shape, mapping):
    raw = Path(path).read_bytes()
    shape = mapping.get('orthophoto_shape', grid_shape)
    if len(raw) > 12*1024*1024 or raw[:8] != b'\x89PNG\r\n\x1a\n' or len(raw) < 24:
        raise ValueError('Ortofoto preparata non valida o troppo grande.')
    width, height = struct.unpack('>II', raw[16:24])
    if not width or not height or max(width, height) > 4096 or width*height > MAX_ORTHOPHOTO_CELLS or [height, width] != list(shape):
        raise ValueError('Ortofoto preparata non coerente con le dimensioni dichiarate.')
    return raw


def load_grid(path):
    # Bound compressed-array expansion before numpy allocates anything.
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != 4 or set(archive.namelist()) != {'z.npy', 'seeds.npy', 'display_mask.npy', 'bounds.npy'} or sum(m.file_size for m in archive.infolist()) > 16*1024*1024:
            raise ValueError('Griglia cartografica non valida o troppo grande.')
    with np.load(path, allow_pickle=False) as data:
        z = data['z']; seeds = data['seeds']; display = data['display_mask']; bounds = data['bounds']
    if z.ndim != 2 or not z.size or z.size > MAX_CELLS or max(z.shape) > 1024 or z.dtype.kind != 'f' or np.isinf(z).any():
        raise ValueError('DEM preparato non valido.')
    if seeds.shape != z.shape or display.shape != z.shape or seeds.dtype != bool or display.dtype != bool:
        raise ValueError('Maschere del DEM non coerenti.')
    if not seeds.any() or not np.isfinite(z[seeds]).all() or not display.any():
        raise ValueError('Mancano celle valide di partenza verso mare o area da rappresentare.')
    if bounds.shape != (4,) or not np.isfinite(bounds).all():
        raise ValueError('Estensione geografica non valida.')
    west, south, east, north = bounds.tolist()
    if not -180 <= west < east <= 180 or not -90 <= south < north <= 90:
        raise ValueError('Estensione geografica non valida.')
    return z, seeds, display, [[south, west], [north, east]]


def connected_mask(z, seeds, level):
    """Eight-neighbour connectivity, as r.lake's 3x3 neighbourhood."""
    if not math.isfinite(level):
        raise ValueError('Quota di propagazione non valida.')
    eligible = np.isfinite(z) & (z < level)
    filled = seeds & eligible
    queue = deque(zip(*np.nonzero(filled)))
    height, width = z.shape
    while queue:
        row, col = queue.popleft()
        for r in range(max(0, row-1), min(height, row+2)):
            for c in range(max(0, col-1), min(width, col+2)):
                if eligible[r, c] and not filled[r, c]:
                    filled[r, c] = True
                    queue.append((r, c))
    return filled


def build_map(unit, bulletin, mapping, root, slug, unit_id):
    from forecast_service.ensemble import STATISTICS_METHOD
    from forecast_service.exposure import is_exposed
    from forecast_service.time_utils import parse_time
    start = parse_time(bulletin.get('display_from', bulletin['processing_started_at'])).replace(minute=0, second=0, microsecond=0)
    from datetime import timedelta
    end = start + timedelta(hours=bulletin['display_hours'])
    if bulletin.get('display_to'):
        end = parse_time(bulletin['display_to'])
    rows = [r for r in unit['hourly'] if start <= parse_time(r['time']) < end]
    expected = [start+timedelta(hours=i) for i in range(bulletin['display_hours'])]
    if [parse_time(r['time']) for r in rows] != expected or any(r.get('statistics_method') != STATISTICS_METHOD or not all(isinstance(r.get(f'twl_p{q}_m'), (int, float)) and math.isfinite(r[f'twl_p{q}_m']) for q in (75, 95)) for r in rows):
        raise ValueError('La mappa richiede tutte le 96 ore e percentili filtrati validi.')
    grid_path = Path(root)/mapping['grid_file']
    z, seeds, display, bounds = load_grid(grid_path)
    prefix = f'maps/{slug}/{unit_id}'
    assets = {}
    layers = []
    for q, color in [(75, (35, 129, 188, 115)), (95, (107, 197, 232, 90))]:
        peak = max(rows, key=lambda r: r[f'twl_p{q}_m'])
        level = peak[f'twl_p{q}_m']
        if not (z[seeds] < level).any():
            raise ValueError('Quota prevista sotto tutte le celle di partenza: spostare i punti di avvio verso mare nel DEM.')
        mask = connected_mask(z, seeds, level) & display
        rgba = np.zeros((*z.shape, 4), dtype=np.uint8)
        rgba[mask] = color
        filename = f'{prefix}-p{q}.png'
        assets[filename] = png_bytes(rgba)
        layers.append({'percentile': q, 'level_m': level, 'peak_time': peak['time'], 'image': 'data/'+filename, 'cells': int(mask.sum())})
    ortho = None
    if mapping.get('orthophoto_file'):
        image = orthophoto_bytes(Path(root)/mapping['orthophoto_file'], z.shape, mapping)
        filename = prefix+'-orthophoto.png'; assets[filename] = image; ortho = 'data/'+filename
    terrain, terrain_scale = None, None
    if not ortho:
        from forecast_service.terrain_background import terrain_background
        image, terrain_scale = terrain_background(z, display)
        filename = prefix+'-terrain.png'; assets[filename] = image; terrain = 'data/'+filename
    exposure = [is_exposed(r.get('direction_deg'), unit.get('wave_exposure')) if r.get('hs_m', 0) > 0 else None for r in rows]
    return {'status': 'available', 'method': METHOD, 'data_mode': bulletin['mode'], 'period_from': start.isoformat(), 'period_to': end.isoformat(),
            'bounds': bounds, 'layers': layers, 'orthophoto': ortho, 'terrain': terrain, 'terrain_scale': terrain_scale,
            'survey_credit': mapping['survey_credit'], 'survey_date': mapping['survey_date'], 'license': mapping['license'],
            'vertical_reference': mapping['vertical_reference'], 'dem_offset_m': mapping['dem_offset_m'],
            'grid_sha256': hashlib.sha256(grid_path.read_bytes()).hexdigest(),
            'hours_non_frontal': exposure.count(False), 'hours_direction_unknown': exposure.count(None),
            'interpretation': 'Estensione statica potenziale, non profondità né probabilità di allagamento. Il runup è intermittente; nessuna trasformazione direzionale o simulazione di sormonto, portate e durata.'}, assets


def write_maps(bulletin, output, root):
    """An unavailable optional map must not suppress the otherwise valid forecast."""
    for slug, location in bulletin['locations'].items():
        for unit_id, unit in [('whole', location), *location.get('sectors', {}).items()]:
            mapping = unit.get('mapping')
            if not mapping:
                continue
            try:
                metadata, assets = build_map(unit, bulletin, mapping, root, slug, unit_id)
            except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
                unit['inundation_map'] = {'status': 'unavailable', 'reason': str(error)}
                continue
            for name, raw in assets.items():
                destination = Path(output)/name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            unit['inundation_map'] = metadata
