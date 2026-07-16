from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


SECTOR_BOUNDS = {
    "All directions": None,
    "N": [(337.5, 360.0), (0.0, 22.5)],
    "NE": [(22.5, 67.5)],
    "E": [(67.5, 112.5)],
    "SE": [(112.5, 157.5)],
    "S": [(157.5, 202.5)],
    "SW": [(202.5, 247.5)],
    "W": [(247.5, 292.5)],
    "NW": [(292.5, 337.5)],
}


def filter_by_sector(df: pd.DataFrame, sector_name: str) -> pd.DataFrame:
    if sector_name == "All directions":
        return df.copy()

    bounds = SECTOR_BOUNDS[sector_name]
    mask = pd.Series(False, index=df.index)

    for lo, hi in bounds:
        mask = mask | ((df["Dir [deg]"] >= lo) & (df["Dir [deg]"] < hi))

    return df.loc[mask].copy()


def extract_storm_maxima(
    df: pd.DataFrame,
    threshold_quantile: float = 0.95,
    min_separation_hours: int = 48,
) -> pd.DataFrame:
    out = df.copy().sort_values("time").reset_index(drop=True)
    out["time"] = pd.to_datetime(out["time"])

    hs_threshold = float(out["Hs [m]"].quantile(threshold_quantile))
    exceed = out[out["Hs [m]"] >= hs_threshold].copy()

    if exceed.empty:
        raise ValueError("No storm peaks found above the selected threshold.")

    storms = []
    current_group = [exceed.iloc[0]]

    for i in range(1, len(exceed)):
        prev_time = pd.to_datetime(current_group[-1]["time"])
        this_row = exceed.iloc[i]
        this_time = pd.to_datetime(this_row["time"])

        delta_h = (this_time - prev_time).total_seconds() / 3600.0

        if delta_h <= min_separation_hours:
            current_group.append(this_row)
        else:
            group_df = pd.DataFrame(current_group)
            storms.append(group_df.loc[group_df["Hs [m]"].idxmax()])
            current_group = [this_row]

    if current_group:
        group_df = pd.DataFrame(current_group)
        storms.append(group_df.loc[group_df["Hs [m]"].idxmax()])

    storm_df = pd.DataFrame(storms).reset_index(drop=True)
    storm_df["threshold_used [m]"] = hs_threshold
    return storm_df


def gumbel_fit_moments(x: np.ndarray) -> Tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]

    if x.size < 5:
        raise ValueError("At least 5 storm maxima are needed for return-value estimation.")

    mean_x = float(np.mean(x))
    std_x = float(np.std(x, ddof=1))

    gamma = 0.5772156649
    beta = std_x * np.sqrt(6) / np.pi
    mu = mean_x - gamma * beta

    return mu, beta


def gumbel_return_value_from_rate(mu: float, beta: float, return_period: float, lambda_year: float) -> float:
    if lambda_year <= 0:
        raise ValueError("Event rate must be positive.")

    non_exceed_prob = 1.0 - 1.0 / (return_period * lambda_year)
    non_exceed_prob = min(max(non_exceed_prob, 1e-6), 0.999999)

    y = -np.log(-np.log(non_exceed_prob))
    return float(mu + beta * y)


def build_return_value_table(
    storm_max_df: pd.DataFrame,
    return_periods: List[int],
) -> pd.DataFrame:
    storm_df = storm_max_df.copy().sort_values("time").reset_index(drop=True)
    storm_df["time"] = pd.to_datetime(storm_df["time"])

    maxima = storm_df["Hs [m]"].to_numpy(dtype=float)
    mu, beta = gumbel_fit_moments(maxima)

    duration_years = max(
        (storm_df["time"].max() - storm_df["time"].min()).days / 365.25,
        1 / 365.25,
    )
    lambda_year = len(storm_df) / duration_years

    x = storm_df["Hs [m]"].to_numpy(dtype=float)
    y = storm_df["Tp [s]"].to_numpy(dtype=float)

    slope, intercept = np.polyfit(x, y, 1)

    rows = []
    for rp in return_periods:
        hs_r = gumbel_return_value_from_rate(mu, beta, rp, lambda_year)
        tp_assoc = intercept + slope * hs_r
        tp_assoc = max(float(tp_assoc), 0.1)

        rows.append(
            {
                "Return period [years]": int(rp),
                "Return Hs [m]": round(float(hs_r), 3),
                "Associated Tp [s]": round(tp_assoc, 3),
            }
        )

    return pd.DataFrame(rows)


def build_sector_max_table(df: pd.DataFrame) -> pd.DataFrame:
    """For each directional sector, report the single largest wave event on record:
    its Hs, associated Tp, direction, and the date/time it occurred."""
    rows = []
    for sector_name in SECTOR_BOUNDS.keys():
        sector_df = filter_by_sector(df, sector_name)
        if sector_df.empty:
            continue

        peak = sector_df.loc[sector_df["Hs [m]"].idxmax()]
        rows.append(
            {
                "Sector": sector_name,
                "Max Hs [m]": round(float(peak["Hs [m]"]), 3),
                "Tp [s]": round(float(peak["Tp [s]"]), 3),
                "Dir [deg]": round(float(peak["Dir [deg]"]), 1),
                "Date": pd.to_datetime(peak["time"]).strftime("%Y-%m-%d %H:%M"),
            }
        )

    return pd.DataFrame(rows)


def summarize_wave_series(df: pd.DataFrame) -> Dict[str, float]:
    return {
        "mean_hs": float(df["Hs [m]"].mean()),
        "max_hs": float(df["Hs [m]"].max()),
        "p90_hs": float(df["Hs [m]"].quantile(0.90)),
        "p95_hs": float(df["Hs [m]"].quantile(0.95)),
        "p99_hs": float(df["Hs [m]"].quantile(0.99)),
    }