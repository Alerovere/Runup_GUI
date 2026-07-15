"""
Fetchers for a single-point, multi-source wave forecast comparison.

Three independent forecast sources are queried for the same point and time
window, then merged into one wide table for cross-checking:

    - Copernicus Marine  - Mediterranean Sea Waves Analysis and Forecast
                            (same product used elsewhere in this app)
    - NOAA WaveWatch III - global forecast, re-published via the PacIOOS
                            ERDDAP mirror (NOAA's own NOMADS OPeNDAP/DODS
                            service for gfswave was retired in Feb 2026 in
                            favor of a GRIB-filter-only interface, so the
                            ERDDAP mirror is used here instead of parsing
                            GRIB2 files directly)
    - Open-Meteo Marine  - free, no-auth aggregator of several global wave
                            models (NOAA GFS-Wave, DWD ICON-Wave, ECMWF WAM)

All three fetchers return a DataFrame with the same column convention used
throughout this app: "time", "Hs [m]", "Tp [s]" (peak period), "Dir [deg]".
"""

from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import List, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import copernicusmarine
except ImportError:
    copernicusmarine = None


MED_WAVE_FORECAST_DATASET_ID = "cmems_mod_med_wav_anfc_4.2km_PT1H-i"

PREFERRED_HS_VARS = ["VHM0", "sea_surface_wave_significant_height"]
PREFERRED_TP_VARS = ["VTPK", "sea_surface_wave_period_at_variance_spectral_density_maximum"]
PREFERRED_DIR_VARS = [
    "VMDR",
    "sea_surface_wave_from_direction",
    "sea_surface_wave_from_direction_at_variance_spectral_density_maximum",
]

NOAA_ERDDAP_BASE = "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/ww3_global"
OPENMETEO_URL = "https://marine-api.open-meteo.com/v1/marine"


def _find_first_present_name(candidates: List[str], names: List[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


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


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_noaa_ww3_forecast(
    longitude: float,
    latitude: float,
    forecast_days: int = 5,
) -> pd.DataFrame:
    """Hs / Tp / Dir forecast at a point from NOAA WaveWatch III (global), via PacIOOS ERDDAP."""
    start_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=forecast_days)

    def iso(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    query = (
        f"Thgt[({iso(start_dt)}):1:({iso(end_dt)})][({latitude}):1:({latitude})][({longitude}):1:({longitude})],"
        f"Tper[({iso(start_dt)}):1:({iso(end_dt)})][({latitude}):1:({latitude})][({longitude}):1:({longitude})],"
        f"Tdir[({iso(start_dt)}):1:({iso(end_dt)})][({latitude}):1:({latitude})][({longitude}):1:({longitude})]"
    )
    url = f"{NOAA_ERDDAP_BASE}.csv?{query}"

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    # ERDDAP CSV: row 0 = column names, row 1 = units, row 2+ = data
    df = pd.read_csv(StringIO(resp.text), skiprows=[1])
    df = df.rename(columns={"Thgt": "Hs [m]", "Tper": "Tp [s]", "Tdir": "Dir [deg]"})
    df = df[["time", "Hs [m]", "Tp [s]", "Dir [deg]"]].dropna()
    df["time"] = pd.to_datetime(df["time"], utc=True)

    if df.empty:
        raise ValueError("No NOAA WaveWatch III records were returned for this point.")

    return df.reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_openmeteo_wave_forecast(
    longitude: float,
    latitude: float,
    forecast_days: int = 5,
) -> pd.DataFrame:
    """Hs / Tp / Dir forecast at a point from the Open-Meteo Marine API (no auth required)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wave_height,wave_peak_period,wave_direction",
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
            "Tp [s]": data.get("wave_peak_period"),
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
        ).set_index("time")

        combined = renamed if combined is None else combined.join(renamed, how="outer")

    if combined is None:
        return pd.DataFrame()

    return combined.sort_index().reset_index()
