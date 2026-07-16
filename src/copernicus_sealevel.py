from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    import copernicusmarine
except ImportError:
    copernicusmarine = None


MED_SEALEVEL_DATASET_ID = "cmems_mod_med_phy-ssh_anfc_4.2km-2D_PT1H-m"

PREFERRED_SSH_VARS = [
    "zos",
    "ssh",
    "sea_surface_height_above_geoid",
]


def _find_first_present_name(candidates: List[str], names: List[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_copernicus_sealevel_timeseries(
    longitude: float,
    latitude: float,
    username: str,
    password: str,
) -> Tuple[pd.DataFrame, str]:
    if copernicusmarine is None:
        raise ImportError("copernicusmarine is not installed.")

    start_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=7)

    ds = copernicusmarine.open_dataset(
        dataset_id=MED_SEALEVEL_DATASET_ID,
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
    ssh_var = _find_first_present_name(PREFERRED_SSH_VARS, data_vars)
    if ssh_var is None:
        raise ValueError(
            f"Sea-level variable not found. Available variables: {data_vars}"
        )

    ssh_da = ds[ssh_var].squeeze()

    for dim in list(ssh_da.dims):
        if dim != "time" and ssh_da.sizes.get(dim, 1) == 1:
            ssh_da = ssh_da.isel({dim: 0})

    df = pd.DataFrame(
        {
            "time": pd.to_datetime(ssh_da["time"].values),
            "ssh [m]": np.asarray(ssh_da.values, dtype=float).reshape(-1),
        }
    ).dropna()

    if df.empty:
        raise ValueError("No sea-level records were returned for this point.")

    mean_ssh = float(df["ssh [m]"].mean())
    df["sea-level signal [m]"] = df["ssh [m]"] - mean_ssh

    return df.reset_index(drop=True), ssh_var


def _normalize_utc(series: pd.Series) -> pd.Series:
    """Coerce a time column to tz-aware UTC at nanosecond resolution, so two
    series built from different sources (or parsed by different pandas
    versions) always compare/merge cleanly. Guards against both tz-naive vs
    tz-aware mismatches and datetime64[ns] vs datetime64[us] MergeErrors."""
    ts = pd.to_datetime(series)
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    return ts.astype("datetime64[ns, UTC]")


def merge_wave_and_sealevel(
    wave_df: pd.DataFrame,
    sealevel_df: pd.DataFrame,
    tolerance: str = "30min",
) -> pd.DataFrame:
    left = wave_df.copy().sort_values("time").reset_index(drop=True)
    right = sealevel_df.copy().sort_values("time").reset_index(drop=True)

    left["time"] = _normalize_utc(left["time"])
    right["time"] = _normalize_utc(right["time"])

    merged = pd.merge_asof(
        left,
        right,
        on="time",
        direction="nearest",
        tolerance=pd.Timedelta(tolerance),
    )

    merged = merged.dropna(subset=["sea-level signal [m]"]).reset_index(drop=True)
    if merged.empty:
        raise ValueError(
            "Wave and sea-level series could not be aligned in time."
        )

    return merged