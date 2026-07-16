"""
Fetchers for a single-point, multi-source wave forecast comparison.

Three independent forecast sources are queried for the same point and time
window, then merged into one wide table for cross-checking:

    - Copernicus Marine  - Mediterranean Sea Waves Analysis and Forecast
                            (same product used elsewhere in this app)
    - NOAA GEFS-Wave      - 31-member global wave ensemble (1 control + 30
                            perturbed members), pulled directly from NOAA's
                            NOMADS GRIB filter and parsed with cfgrib. NOAA's
                            NOMADS OPeNDAP/DODS service (and any ERDDAP mirror
                            depending on it) was retired in Feb 2026, so the
                            GRIB filter is now the only live route to this
                            data; there is no bulk CSV/OPeNDAP shortcut, which
                            means one HTTP request per member per forecast
                            hour. Requests are parallelized, but expect this
                            source to take noticeably longer than the other two.
    - Open-Meteo Marine  - free, no-auth aggregator of several global wave
                            models (NOAA GFS-Wave, DWD ICON-Wave, ECMWF WAM)

All fetchers return a DataFrame with the column convention used throughout
this app: "time", "Hs [m]", "Tp [s]", "Dir [deg]".
"""

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import copernicusmarine
except ImportError:
    copernicusmarine = None

try:
    import xarray as xr
except ImportError:
    xr = None


MED_WAVE_FORECAST_DATASET_ID = "cmems_mod_med_wav_anfc_4.2km_PT1H-i"

PREFERRED_HS_VARS = ["VHM0", "sea_surface_wave_significant_height"]
PREFERRED_TP_VARS = ["VTPK", "sea_surface_wave_period_at_variance_spectral_density_maximum"]
PREFERRED_DIR_VARS = [
    "VMDR",
    "sea_surface_wave_from_direction",
    "sea_surface_wave_from_direction_at_variance_spectral_density_maximum",
]

OPENMETEO_URL = "https://marine-api.open-meteo.com/v1/marine"

# NOAA GEFS-Wave ensemble (31 members, 0.25 deg global), via NOMADS GRIB filter
NOAA_GRIB_FILTER_URL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_wave_0p25.pl"
GEFS_WAVE_MEMBERS = ["c00"] + [f"p{i:02d}" for i in range(1, 31)]  # 1 control + 30 perturbed = 31
GEFS_WAVE_FORECAST_HOURS = list(range(0, 97, 6))  # every 6h out to 4 days = 17 steps
GEFS_WAVE_CYCLE_LAG_HOURS = 5  # processing/publication delay after each 00/06/12/18Z cycle
GEFS_WAVE_MAX_WORKERS = 8


def _find_first_present_name(candidates: List[str], names: List[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


def _normalize_utc(series: pd.Series) -> pd.Series:
    """Coerce a time column to tz-aware UTC at nanosecond resolution, regardless
    of how the source returned it. Two separate mismatches show up here in
    practice:

    1. tz-naive vs tz-aware: the Copernicus sea-level fetcher (src.copernicus_sealevel)
       returns tz-naive timestamps, while every wave fetcher in this module
       returns tz-aware UTC. Comparing or subtracting the two raises "Cannot
       compare tz-naive and tz-aware timestamps".
    2. datetime64[ns] vs datetime64[us]: depending on the pandas/Python version,
       parsing timestamps from different sources (e.g. a date_range vs JSON API
       strings vs GRIB-derived arrays) can land on different underlying time
       resolutions. Newer pandas versions raise a hard MergeError
       ("incompatible merge keys ... must be the same type") on merge_asof if
       the two sides don't match exactly, even if both are tz-aware UTC.

    Explicitly casting to a single canonical dtype here avoids both.
    """
    ts = pd.to_datetime(series)
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    return ts.astype("datetime64[ns, UTC]")


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_copernicus_med_wave_forecast(
    longitude: float,
    latitude: float,
    username: str,
    password: str,
    forecast_days: int = 5,
) -> pd.DataFrame:
    """Hs / Tp / Dir forecast at a point from the Copernicus Mediterranean wave product."""
    if copernicusmarine is None:
        raise ImportError("copernicusmarine is not installed.")

    start_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=forecast_days)

    ds = copernicusmarine.open_dataset(
        dataset_id=MED_WAVE_FORECAST_DATASET_ID,
        minimum_longitude=longitude,
        maximum_longitude=longitude,
        minimum_latitude=latitude,
        maximum_latitude=latitude,
        start_datetime=start_dt.isoformat(),
        end_datetime=end_dt.isoformat(),
        username=username,
        password=password,
    )

    data_vars = list(ds.data_vars)
    hs_var = _find_first_present_name(PREFERRED_HS_VARS, data_vars)
    tp_var = _find_first_present_name(PREFERRED_TP_VARS, data_vars)
    dir_var = _find_first_present_name(PREFERRED_DIR_VARS, data_vars)

    missing = [
        name
        for name, var in [("Hs", hs_var), ("Tp", tp_var), ("Direction", dir_var)]
        if var is None
    ]
    if missing:
        raise ValueError(f"Missing required wave variable(s): {', '.join(missing)}. Available: {data_vars}")

    hs_da, tp_da, dir_da = ds[hs_var].squeeze(), ds[tp_var].squeeze(), ds[dir_var].squeeze()
    for da_name, da in [("hs", hs_da), ("tp", tp_da), ("dir", dir_da)]:
        for dim in list(da.dims):
            if dim != "time" and da.sizes.get(dim, 1) == 1:
                if da_name == "hs":
                    hs_da = hs_da.isel({dim: 0})
                elif da_name == "tp":
                    tp_da = tp_da.isel({dim: 0})
                else:
                    dir_da = dir_da.isel({dim: 0})

    df = pd.DataFrame(
        {
            "time": pd.to_datetime(hs_da["time"].values, utc=True),
            "Hs [m]": np.asarray(hs_da.values, dtype=float).reshape(-1),
            "Tp [s]": np.asarray(tp_da.values, dtype=float).reshape(-1),
            "Dir [deg]": np.asarray(dir_da.values, dtype=float).reshape(-1),
        }
    ).dropna()

    if df.empty:
        raise ValueError("No forecast records were returned for this point.")

    return df.reset_index(drop=True)


def _latest_gefs_wave_cycle() -> tuple:
    """Most recent GEFS-Wave cycle (00/06/12/18Z) that should already be published."""
    lagged = datetime.now(timezone.utc) - timedelta(hours=GEFS_WAVE_CYCLE_LAG_HOURS)
    cycle_hour = (lagged.hour // 6) * 6
    cycle_date = lagged.strftime("%Y%m%d")
    return cycle_date, cycle_hour


def _circular_mean_deg(degrees: np.ndarray) -> float:
    radians = np.deg2rad(degrees)
    mean_angle = np.arctan2(np.nanmean(np.sin(radians)), np.nanmean(np.cos(radians)))
    return float(np.rad2deg(mean_angle) % 360.0)


def _fetch_one_gefs_wave_member_hour(
    cycle_date: str,
    cycle_hour: int,
    member: str,
    forecast_hour: int,
    longitude: float,
    latitude: float,
    buffer_deg: float = 1.0,
):
    """Download one small GRIB2 subset (1 member, 1 forecast hour, cropped to the point) and parse it."""
    if xr is None:
        raise ImportError("xarray is not installed.")

    lon_360 = longitude % 360.0
    params = {
        "dir": f"/gefs.{cycle_date}/{cycle_hour:02d}/wave/gridded",
        "file": f"gefs.wave.t{cycle_hour:02d}z.{member}.global.0p25.f{forecast_hour:03d}.grib2",
        "var_HTSGW": "on",
        "var_PERPW": "on",
        "var_DIRPW": "on",
        "lev_surface": "on",
        "subregion": "",
        "leftlon": round(lon_360 - buffer_deg, 2),
        "rightlon": round(lon_360 + buffer_deg, 2),
        "toplat": round(latitude + buffer_deg, 2),
        "bottomlat": round(latitude - buffer_deg, 2),
    }

    resp = requests.get(NOAA_GRIB_FILTER_URL, params=params, timeout=60)
    resp.raise_for_status()

    if len(resp.content) < 100:
        # Too small to be a real GRIB2 message; this member/hour is unavailable.
        return None

    with tempfile.NamedTemporaryFile(suffix=".grib2") as tmp:
        tmp.write(resp.content)
        tmp.flush()
        ds = xr.open_dataset(tmp.name, engine="cfgrib", backend_kwargs={"indexpath": ""})

        lon_vals = ds["longitude"].values
        target_lon = lon_360 if np.nanmax(lon_vals) > 180 else (((longitude + 180) % 360) - 180)

        point = ds.sel(latitude=latitude, longitude=target_lon, method="nearest")

        valid_time = pd.to_datetime(point["valid_time"].values, utc=True)
        hs = float(point["swh"].values) if "swh" in point else np.nan
        tp = float(point["perpw"].values) if "perpw" in point else np.nan
        wave_dir = float(point["dirpw"].values) if "dirpw" in point else np.nan

    return {
        "time": valid_time,
        "Model": member,
        "Hs [m]": hs,
        "Tp [s]": tp,
        "Dir [deg]": wave_dir,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_noaa_gefs_wave_ensemble(
    longitude: float,
    latitude: float,
    forecast_days: int = 5,
) -> "tuple[pd.DataFrame, pd.DataFrame, dict]":
    """
    Full 31-member NOAA GEFS-Wave ensemble at a point.

    Returns (detail_df, summary_df, metadata):
      - detail_df: one row per (member, forecast hour) with columns
        time, Model (member id), Hs [m], Tp [s], Dir [deg]
      - summary_df: ensemble mean/min/max per forecast hour, columns
        time, Hs [m], Tp [s], Dir [deg] (Hs/Tp are the ensemble mean;
        Hs min/max are also included for the spread plot)
      - metadata: cycle date/hour used and how many member-hour requests
        succeeded out of how many were attempted
    """
    cycle_date, cycle_hour = _latest_gefs_wave_cycle()

    max_hour = min(int(forecast_days) * 24, max(GEFS_WAVE_FORECAST_HOURS))
    forecast_hours = [h for h in GEFS_WAVE_FORECAST_HOURS if h <= max_hour]

    tasks = [
        (cycle_date, cycle_hour, member, fhour, longitude, latitude)
        for member in GEFS_WAVE_MEMBERS
        for fhour in forecast_hours
    ]

    rows = []
    failures = 0

    with ThreadPoolExecutor(max_workers=GEFS_WAVE_MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_one_gefs_wave_member_hour, *task): task for task in tasks}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    rows.append(result)
                else:
                    failures += 1
            except Exception:
                failures += 1

    metadata = {
        "cycle_date": cycle_date,
        "cycle_hour": cycle_hour,
        "requested": len(tasks),
        "succeeded": len(rows),
        "failed": failures,
    }

    if not rows:
        raise ValueError(
            f"No GEFS-Wave ensemble records were returned for this point (cycle {cycle_date} {cycle_hour:02d}Z)."
        )

    detail_df = pd.DataFrame(rows).dropna(subset=["Hs [m]"]).sort_values(["time", "Model"]).reset_index(drop=True)

    if detail_df.empty:
        raise ValueError("GEFS-Wave ensemble requests succeeded but returned no usable values.")

    summary_df = summarize_ensemble_detail(detail_df)

    return detail_df, summary_df, metadata


def summarize_ensemble_detail(detail_df: pd.DataFrame) -> pd.DataFrame:
    """Per-timestep ensemble mean/min/max Hs, mean Tp, circular-mean Dir, and
    member count, from a per-member detail table (time, Model, Hs [m], Tp [s], Dir [deg])."""
    summary_rows = []
    for time_val, group in detail_df.groupby("time"):
        summary_rows.append(
            {
                "time": time_val,
                "Hs [m]": float(group["Hs [m]"].mean()),
                "Hs min [m]": float(group["Hs [m]"].min()),
                "Hs max [m]": float(group["Hs [m]"].max()),
                "Tp [s]": float(group["Tp [s]"].mean()),
                "Dir [deg]": _circular_mean_deg(group["Dir [deg]"].to_numpy(dtype=float)),
                "Members": int(group["Model"].nunique()),
            }
        )

    return pd.DataFrame(summary_rows).sort_values("time").reset_index(drop=True)


def build_shared_hourly_grid(dfs: List[pd.DataFrame], freq: str = "1h") -> Optional[pd.DatetimeIndex]:
    """Union hourly time grid spanning every given source's own time range, so all
    sources can be spline-interpolated onto exactly the same timestamps. Each
    source keeps its own true coverage (interpolation elsewhere in this module
    never extrapolates), so this just fixes the *timestamps* everyone lines up on."""
    valid = [df for df in dfs if df is not None and not df.empty]
    if not valid:
        return None

    normalized_times = [_normalize_utc(df["time"]) for df in valid]
    start = min(t.min() for t in normalized_times)
    end = max(t.max() for t in normalized_times)

    return pd.date_range(start=start, end=end, freq=freq, tz="UTC")


def interpolate_series_to_grid(
    df: pd.DataFrame,
    time_grid: pd.DatetimeIndex,
    value_cols: tuple = ("Hs [m]", "Tp [s]"),
    circular_cols: tuple = ("Dir [deg]",),
) -> pd.DataFrame:
    """Spline-interpolate a single deterministic series (e.g. Copernicus,
    Open-Meteo, or a sea-level signal) onto a shared time grid, so every source
    lines up on exactly the same timestamps. Values outside this series' own
    time range are left as NaN (no extrapolation). Circular columns (e.g.
    direction) are nearest-held instead of splined."""
    if df is None or df.empty or time_grid is None or len(time_grid) == 0:
        return pd.DataFrame({"time": time_grid}) if time_grid is not None else pd.DataFrame()

    from scipy.interpolate import CubicSpline

    g = df.sort_values("time").reset_index(drop=True)
    g["time"] = _normalize_utc(g["time"])

    grid = _normalize_utc(pd.Series(time_grid))

    t0 = g["time"].iloc[0]
    x = (g["time"] - t0).dt.total_seconds().to_numpy()
    grid_x = (grid - t0).dt.total_seconds().to_numpy()
    in_range = (grid_x >= x[0]) & (grid_x <= x[-1])

    out = pd.DataFrame({"time": grid})

    for col in value_cols:
        if col not in g.columns:
            continue
        values = np.full(len(grid), np.nan)
        if in_range.any():
            if len(x) >= 3:
                spline = CubicSpline(x, g[col].to_numpy())
                values[in_range] = spline(grid_x[in_range])
            else:
                values[in_range] = np.interp(grid_x[in_range], x, g[col].to_numpy())
        out[col] = values

    for col in circular_cols:
        if col not in g.columns:
            continue
        merged = pd.merge_asof(
            pd.DataFrame({"time": grid}).sort_values("time"),
            g[["time", col]].sort_values("time"),
            on="time",
            direction="nearest",
        )
        values = merged[col].to_numpy()
        values = np.where(in_range, values, np.nan)
        out[col] = values

    return out.dropna(subset=[c for c in value_cols if c in out.columns], how="all").reset_index(drop=True)


def interpolate_ensemble_to_hourly(
    detail_df: pd.DataFrame,
    freq: str = "1h",
    time_grid: Optional[pd.DatetimeIndex] = None,
) -> pd.DataFrame:
    """Interpolate each ensemble member's Hs/Tp series onto an hourly grid with a
    cubic spline, per member.

    The NOAA GEFS-Wave ensemble is only available every 6 hours, while Copernicus
    and Open-Meteo are hourly. Combining them directly means the set of estimates
    feeding the combined runup band changes abruptly every 6 hours (many more,
    wider-spread NOAA-derived estimates suddenly appear), which shows up as
    spikes in the combined band. Interpolating each member first removes that
    composition jump; only interpolation within each member's own known time
    range is used (no extrapolation).

    If time_grid is given, every member is interpolated onto that same shared
    grid (so it lines up exactly with other sources interpolated the same way).
    Otherwise each member gets its own hourly grid starting at its own first
    timestamp.
    """
    if detail_df is None or detail_df.empty:
        return detail_df

    from scipy.interpolate import CubicSpline

    step_seconds = pd.Timedelta(freq).total_seconds()
    out_frames = []

    grid_normalized = _normalize_utc(pd.Series(time_grid)) if time_grid is not None else None

    for member, group in detail_df.groupby("Model"):
        g = group.sort_values("time").reset_index(drop=True)
        g["time"] = _normalize_utc(g["time"])

        if len(g) < 3:
            # Not enough points for a cubic spline; keep this member as-is.
            out_frames.append(g)
            continue

        t0 = g["time"].iloc[0]
        x = (g["time"] - t0).dt.total_seconds().to_numpy()

        if grid_normalized is not None:
            grid_x = (grid_normalized - t0).dt.total_seconds().to_numpy()
            in_range = (grid_x >= x[0]) & (grid_x <= x[-1])
            new_x = grid_x[in_range]
            new_time = grid_normalized.to_numpy()[in_range]
        else:
            new_x = np.arange(x[0], x[-1] + 1e-6, step_seconds)
            new_time = t0 + pd.to_timedelta(new_x, unit="s")

        if len(new_x) == 0:
            continue

        interp = pd.DataFrame({"time": new_time, "Model": member})
        for col in ["Hs [m]", "Tp [s]"]:
            spline = CubicSpline(x, g[col].to_numpy())
            interp[col] = spline(new_x)

        if "Dir [deg]" in g.columns:
            # Direction is circular, so hold the nearest observed value rather
            # than splining an angle (which breaks down across the 0/360 wrap).
            interp = pd.merge_asof(
                interp.sort_values("time"),
                g[["time", "Dir [deg]"]].sort_values("time"),
                on="time",
                direction="nearest",
            )

        out_frames.append(interp)

    if not out_frames:
        return detail_df.iloc[0:0]

    return pd.concat(out_frames, ignore_index=True).sort_values(["time", "Model"]).reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_openmeteo_wave_forecast(
    longitude: float,
    latitude: float,
    forecast_days: int = 5,
) -> pd.DataFrame:
    """Hs / Tp / Dir forecast at a point from the Open-Meteo Marine API (no auth required).

    Note: Open-Meteo's combined "wave_period" field is a mean period across the
    combined wind-sea + swell spectrum, not strictly the spectral peak period.
    A dedicated peak-period field only exists for the wind-sea and swell
    partitions separately (wind_wave_peak_period / swell_wave_peak_period),
    not for the combined field, so "wave_period" is the closest available match.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wave_height,wave_period,wave_direction",
        "forecast_days": max(1, min(int(forecast_days), 7)),
        "timezone": "UTC",
    }
    resp = requests.get(OPENMETEO_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json().get("hourly", {})

    if not data or "time" not in data:
        raise ValueError("Open-Meteo Marine returned no hourly data for this point.")

    df = pd.DataFrame(
        {
            "time": pd.to_datetime(data["time"], utc=True),
            "Hs [m]": data.get("wave_height"),
            "Tp [s]": data.get("wave_period"),
            "Dir [deg]": data.get("wave_direction"),
        }
    ).dropna()

    if df.empty:
        raise ValueError("No Open-Meteo Marine records were returned for this point.")

    return df.reset_index(drop=True)


def merge_multi_source(source_frames: dict) -> pd.DataFrame:
    """Outer-join per-source Hs/Tp/Dir DataFrames on time into one wide comparison table."""
    combined = None
    for source_name, df in source_frames.items():
        renamed = df.rename(
            columns={
                "Hs [m]": f"{source_name} Hs [m]",
                "Tp [s]": f"{source_name} Tp [s]",
                "Dir [deg]": f"{source_name} Dir [deg]",
            }
        )[["time", f"{source_name} Hs [m]", f"{source_name} Tp [s]", f"{source_name} Dir [deg]"]].copy()

        # Defensive: every source is expected to already return tz-aware UTC timestamps
        # at the same resolution, but a mismatch here (tz-naive vs tz-aware, or
        # datetime64[ns] vs datetime64[us]) raises an unhelpful pandas error on join,
        # so normalize defensively rather than letting one source silently break the
        # whole page.
        renamed["time"] = _normalize_utc(renamed["time"])
        renamed = renamed.set_index("time")

        combined = renamed if combined is None else combined.join(renamed, how="outer")

    if combined is None:
        return pd.DataFrame()

    return combined.sort_index().reset_index()
