from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    import copernicusmarine
except ImportError:
    copernicusmarine = None


MED_DATASET_ID = "cmems_mod_med_wav_anfc_4.2km_PT1H-i"

PREFERRED_HS_VARS = [
    "VHM0",
    "Vm0",
    "sea_surface_wave_significant_height",
]

PREFERRED_PEAK_PERIOD_VARS = [
    "VTPK",
    "sea_surface_wave_period_at_variance_spectral_density_maximum",
]


def _find_first_present_name(candidates: List[str], names: List[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_copernicus_wave_timeseries(
    longitude: float,
    latitude: float,
    username: str,
    password: str,
) -> Tuple[pd.DataFrame, str, str]:
    if copernicusmarine is None:
        raise ImportError("copernicusmarine is not installed.")

    start_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=7)

    ds = copernicusmarine.open_dataset(
        dataset_id=MED_DATASET_ID,
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
    if hs_var is None:
        raise ValueError(f"Hs variable not found. Available variables: {data_vars}")

    period_var = _find_first_present_name(PREFERRED_PEAK_PERIOD_VARS, data_vars)
    if period_var is None:
        raise ValueError(f"Peak-period variable not found. Available variables: {data_vars}")

    hs_da = ds[hs_var].squeeze()
    tp_da = ds[period_var].squeeze()

    for dim in list(hs_da.dims):
        if dim != "time" and hs_da.sizes.get(dim, 1) == 1:
            hs_da = hs_da.isel({dim: 0})

    for dim in list(tp_da.dims):
        if dim != "time" and tp_da.sizes.get(dim, 1) == 1:
            tp_da = tp_da.isel({dim: 0})

    df = pd.DataFrame(
        {
            "time": pd.to_datetime(hs_da["time"].values),
            "Hs [m]": np.asarray(hs_da.values, dtype=float).reshape(-1),
            "Tp [s]": np.asarray(tp_da.values, dtype=float).reshape(-1),
        }
    ).dropna()

    if df.empty:
        raise ValueError("No forecast records were returned for this point.")

    return df.reset_index(drop=True), hs_var, period_var