"""Colour the existing prepared DEM for display only; leave NoData transparent."""
import numpy as np

from forecast_service.inundation import png_bytes

COLORS = ['#f5f4e1', '#d3e0af', '#98b179', '#b29568', '#7f644b']


def terrain_background(z, display):
    z = np.asarray(z)
    valid = np.isfinite(z) & np.asarray(display, dtype=bool)
    if not valid.any():
        raise ValueError('Nessuna quota DEM valida nell’area da mostrare.')
    low, high = np.quantile(z[valid], [.02, .98]).tolist()
    if high <= low:
        low, high = float(z[valid].min()), float(z[valid].max())
    rgba = np.zeros((*z.shape, 4), dtype=np.uint8)
    scale = np.zeros(z.shape, dtype=float)
    if high > low:
        scale[valid] = np.clip((z[valid]-low)/(high-low), 0., 1.)
    rgb = np.array([[int(color[i:i+2],16) for i in (1,3,5)] for color in COLORS])
    for channel in range(3):
        rgba[:,:,channel][valid] = np.interp(scale[valid], np.linspace(0,1,len(COLORS)),rgb[:,channel]).round().astype(np.uint8)
    rgba[:,:,3][valid] = 255
    return png_bytes(rgba), dict(min_m=low,max_m=high,colors=COLORS,
        label='Quota del terreno (m)',scale_note='Colori saturati sotto il 2° e sopra il 98° percentile delle quote; le quote di calcolo non cambiano.')
