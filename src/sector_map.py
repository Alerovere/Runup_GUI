"""
Small folium-based map helper that shows a directional sector as a wedge
(pie-slice) centered on an offshore point, so the compass sector selected for
filtering wave data (e.g. in the Wave Explorer or Runup Forecast pages) can be
seen visually rather than just read off a dropdown.

Direction convention matches the rest of this app ("Dir [deg]" is the compass
bearing the waves are coming FROM), so the wedge points outward from the site
toward the sector it represents - i.e. it shows where the offshore wave energy
originates, not where it is heading.
"""

import math
from typing import List, Tuple, Union

import folium

from src.extremes import SECTOR_BOUNDS


def _destination_point(lat: float, lon: float, bearing_deg: float, distance_km: float) -> Tuple[float, float]:
    """Approximate destination point given a start point, compass bearing, and
    great-circle distance (spherical-earth formula; accurate enough for the
    regional map-preview zoom levels used here)."""
    r_earth = 6371.0
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    d_r = distance_km / r_earth

    lat2 = math.asin(math.sin(lat1) * math.cos(d_r) + math.cos(lat1) * math.sin(d_r) * math.cos(bearing))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(d_r) * math.cos(lat1),
        math.cos(d_r) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def _sector_arc_bounds(sector_name: str) -> Tuple[float, float]:
    """Continuous (lo, hi) bearing range for a sector, normalizing the N sector
    (which wraps across 0/360 in SECTOR_BOUNDS) to e.g. (-22.5, 22.5)."""
    bounds = SECTOR_BOUNDS[sector_name]
    if sector_name == "N":
        return -22.5, 22.5
    lo, hi = bounds[0]
    return lo, hi


def build_sector_map(
    lat: float,
    lon: float,
    sector_name: Union[str, List[str]] = "All directions",
    radius_km: float = 60.0,
    zoom_start: int = 7,
) -> folium.Map:
    """Map centered on (lat, lon) with a marker at the point, and either a full
    circle ("All directions") or one wedge per selected compass sector, so the
    directional filter applied to the wave/runup data is visible on the map
    itself. sector_name accepts either a single sector name or a list of several
    - each selected sector gets its own wedge, so a combined selection like
    ["SW", "W"] is drawn as two adjoining wedges rather than one merged shape."""
    sector_names = [sector_name] if isinstance(sector_name, str) else list(sector_name)
    fmap = folium.Map(location=[lat, lon], zoom_start=zoom_start, tiles="CartoDB positron")

    folium.Marker(
        location=[lat, lon],
        tooltip=f"lat = {lat:.5f}, lon = {lon:.5f}",
    ).add_to(fmap)

    if not sector_names or "All directions" in sector_names:
        folium.Circle(
            location=[lat, lon],
            radius=radius_km * 1000.0,
            color="#0b5cad",
            weight=1.5,
            fill=True,
            fill_color="#4f9be6",
            fill_opacity=0.15,
            tooltip="All directions considered",
        ).add_to(fmap)
        return fmap

    for name in sector_names:
        lo, hi = _sector_arc_bounds(name)
        bearings: List[float] = [lo + (hi - lo) * i / 24 for i in range(25)]
        arc_points = [_destination_point(lat, lon, b, radius_km) for b in bearings]

        polygon_points = [(lat, lon)] + arc_points + [(lat, lon)]

        folium.Polygon(
            locations=polygon_points,
            color="#0b5cad",
            weight=1.5,
            fill=True,
            fill_color="#4f9be6",
            fill_opacity=0.35,
            tooltip=f"{name} sector (waves coming from this direction)",
        ).add_to(fmap)

    return fmap
