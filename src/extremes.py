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


def annual_maxima(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["year"] = pd.to_datetime(out["time"]).dt.year

    idx = out.groupby("year")["Hs [m]"].idxmax()
    maxima = out.loc[idx].sort_values("year").reset_index(drop=True)
    return maxima


def gumbel_fit_moments(x: np.ndarray) -> Tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]

    if x.size < 3:
        raise ValueError("At least 3 annual maxima are needed for return-value estimation.")

    mean_x = float(np.mean(x))
    std_x = float(np.std(x, ddof=1))

    gamma = 0.5772156649
    beta = std_x * np.sqrt(6) / np.pi
    mu = mean_x - gamma * beta

    return mu, beta


def gumbel_return_value(mu: float, beta: float, return_period: float) -> float:
    f = 1.0 - 1.0 / float(return_period)
    y = -np.log(-np.log(f))
    return float(mu + beta * y)


def build_return_value_table(
    annual_max_df: pd.DataFrame,
    return_periods: List[int],
    n_associated: int = 3,
) -> pd.DataFrame:
    maxima = annual_max_df["Hs [m]"].to_numpy(dtype=float)
    mu, beta = gumbel_fit_moments(maxima)

    rows = []
    for rp in return_periods:
        hs_r = gumbel_return_value(mu, beta, rp)

        annual_max_df = annual_max_df.copy()
        annual_max_df["hs_diff"] = np.abs(annual_max_df["Hs [m]"] - hs_r)
        nearest = annual_max_df.nsmallest(n_associated, "hs_diff")

        assoc_tp = float(nearest["Tp [s]"].median())

        rows.append(
            {
                "Return period [years]": int(rp),
                "Return Hs [m]": round(hs_r, 3),
                "Associated Tp [s]": round(assoc_tp, 3),
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