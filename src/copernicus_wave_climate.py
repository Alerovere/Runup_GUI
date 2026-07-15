from datetime import date
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    import copernicusmarine
except ImportError:
    copernicusmarine = None


MED_WAVE_MULTIYEAR_DATASET_ID = "cmems_mod_med_wav_my_4.2km_PT1H-i"
GLOBAL_WAVE_MULTIYEAR_DATASET_ID = "cmems_mod_glo_wav_my_0.2deg_PT3H-i"

# Region choices exposed to the Wave Explorer page. Each entry carries the dataset id,
# a human-readable product name/DOI for citation, and the known temporal coverage of the
# reanalysis so the page can set sensible date-picker defaults/limits per region.
REGIONS = {
    "Mediterranean": {
        "dataset_id": MED_WAVE_MULTIYEAR_DATASET_ID,
        "product_name": "Mediterranean Sea Waves Reanalysis",
        "product_id": "MEDSEA_MULTIYEAR_WAV_006_012",
        "doi": "10.25423/CMCC/MEDSEA_MULTIYEAR_WAV_006_012",
        "coverage_start": date(1985, 1, 1),
        "coverage_end": date(2024, 12, 31),
        "bbox": (30.0, 46.5, -6.5, 37.0),  # (min_lat, max_lat, min_lon, max_lon)
    },
    "Global": {
        "dataset_id": GLOBAL_WAVE_MULTIYEAR_DATASET_ID,
        "product_name": "Global Ocean Waves Reanalysis (WAVERYS)",
        "product_id": "GLOBAL_MULTIYEAR_WAV_001_032",
        "doi": "10.48670/moi-00022",
        "coverage_start": date(1980, 1, 1),
        "coverage_end": date(2026, 3, 31),
        "bbox": (-89.8, 89.8, -180.0, 179.8),
    },
}

PREFERRED_HS_VARS = [
    "VHM0",
    "sea_surface_wave_significant_height",
]

PREFERRED_TP_VARS = [
    "VTPK",
    "sea_surface_wave_period_at_variance_spectral_density_maximum",
]

PREFERRED_DIR_VARS = [
    "VMDR",
    "sea_surface_wave_from_direction",
    "sea_surface_wave_from_direction_at_variance_spectral_density_maximum",
]


def _find_first_present_name(candidates: List[str], names: List[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_copernicus_wave_climate_timeseries(
    longitude: float,
    latitude: float,
    start_date: date,
    end_date: date,
    username: str,
    password: str,
    dataset_id: str = MED_WAVE_MULTIYEAR_DATASET_ID,
) -> Tuple[pd.DataFrame, dict]:
    if copernicusmarine is None:
        raise ImportError("copernicusmarine is not installed.")

    ds = copernicusmarine.open_dataset(
        dataset_id=dataset_id,
        minimum_longitude=longitude,
        maximum_longitude=longitude,
        minimum_latitude=latitude,
        maximum_latitude=latitude,
        start_datetime=f"{start_date.isoformat()}T00:00:00Z",
        end_datetime=f"{end_date.isoformat()}T23:00:00Z",
        username=username,
        password=password,
    )

    data_vars = list(ds.data_vars)

    hs_var = _find_first_present_name(PREFERRED_HS_VARS, data_vars)
    tp_var = _find_first_present_name(PREFERRED_TP_VARS, data_vars)
    dir_var = _find_first_present_name(PREFERRED_DIR_VARS, data_vars)

    missing = []
    if hs_var is None:
        missing.append("Hs")
    if tp_var is None:
        missing.append("Tp")
    if dir_var is None:
        missing.append("Direction")
    if missing:
        raise ValueError(
            f"Missing required wave variable(s): {', '.join(missing)}. Available variables: {data_vars}"
        )

    hs_da = ds[hs_var].squeeze()
    tp_da = ds[tp_var].squeeze()
    dir_da = ds[dir_var].squeeze()

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
            "time": pd.to_datetime(hs_da["time"].values),
            "Hs [m]": np.asarray(hs_da.values, dtype=float).reshape(-1),
            "Tp [s]": np.asarray(tp_da.values, dtype=float).reshape(-1),
            "Dir [deg]": np.asarray(dir_da.values, dtype=float).reshape(-1),
        }
    ).dropna()

    if df.empty:
        raise ValueError("No wave-climate records were returned for this point.")

    metadata = {
        "dataset_id": dataset_id,
        "hs_var": hs_var,
        "tp_var": tp_var,
        "dir_var": dir_var,
    }

    return df.reset_index(drop=True), metadata
