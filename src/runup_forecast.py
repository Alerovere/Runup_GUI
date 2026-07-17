"""
Helpers that turn one or more single-point wave-forecast sources into a combined
runup / total-water-level forecast, by running every empirical model in
py-wave-runup (via src.runup_models.compute_runup) against every source's Hs/Tp
series.

Sources are treated as follows:
  - Deterministic single-series sources (Copernicus, Open-Meteo): one row per
    timestamp, run through every runup model once.
  - The NOAA GEFS-Wave ensemble (31 members): every member is run through every
    runup model individually, so the ensemble's own internal spread feeds into
    the combined runup band alongside the empirical-model spread, rather than
    collapsing NOAA down to a single ensemble-mean series first.

The result is one long "detail" table (time, Source, Member, Runup model, Model,
Hs, Tp, Water level, Runup, Total water level) that plugs directly into the
existing src.forecast_thresholds traffic-light helpers and the
plot_forecast_model_timeseries plot, exactly like the single-source Mediterranean
forecast used to.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.copernicus_sealevel import merge_wave_and_sealevel
from src.runup_models import RunupInputs, compute_runup


def _normalize_utc(series: pd.Series) -> pd.Series:
    """Coerce a time column to tz-aware UTC at nanosecond resolution.

    Two separate mismatches show up in practice: tz-naive vs tz-aware (the
    Copernicus sea-level fetcher returns tz-naive timestamps, other sources
    don't), and datetime64[ns] vs datetime64[us] (different sources/pandas
    versions can resolve timestamps to different underlying resolutions, which
    newer pandas raises a hard MergeError on during merge_asof). Casting to one
    canonical dtype here avoids both.
    """
    ts = pd.to_datetime(series)
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    return ts.astype("datetime64[ns, UTC]")


def compute_multi_source_runup_detail(
    source_wave_frames: Dict[str, pd.DataFrame],
    slope: float,
    water_level_mode: str,
    constant_eta: float = 0.0,
    sealevel_df: Optional[pd.DataFrame] = None,
    noaa_detail_df: Optional[pd.DataFrame] = None,
    sealevel_tolerance: str = "30min",
) -> tuple[pd.DataFrame, int]:
    """Run every runup model against every source's Hs/Tp series.

    source_wave_frames: deterministic single-series sources, each a DataFrame
    with columns time / Hs [m] / Tp [s] (e.g. {"Copernicus": df, "Open-Meteo": df}).

    noaa_detail_df: optional NOAA GEFS-Wave ensemble detail table, one row per
    member per forecast hour, with columns time / Model (member id) / Hs [m] / Tp [s].
    When given, every member is run through every runup model individually.

    water_level_mode == "Copernicus mean-removed sea-level signal" applies
    sealevel_df (columns time / sea-level signal [m]) via a nearest-time merge;
    any other value uses a constant eta for every row.

    Returns (detail_df, skipped_row_count). Rows with a non-physical Hs/Tp (<= 0 -
    a genuinely flat/calm sea reported by a source, or an occasional cubic-spline
    interpolation overshoot near zero) are skipped rather than allowed to crash the
    whole page, since validate_inputs() rejects them; skipped_row_count lets the
    caller surface how many timesteps/models were dropped this way.
    """
    use_sealevel = (
        water_level_mode == "Copernicus mean-removed sea-level signal"
        and sealevel_df is not None
        and not sealevel_df.empty
    )

    sealevel_norm = None
    if use_sealevel:
        sealevel_norm = sealevel_df.copy()
        sealevel_norm["time"] = _normalize_utc(sealevel_norm["time"])

    rows = []
    skipped_count = 0

    def _process(source_name: str, df: pd.DataFrame, member_col: Optional[str] = None) -> None:
        nonlocal skipped_count
        if df is None or df.empty:
            return

        work = df.copy()
        work["time"] = _normalize_utc(work["time"])

        eta_col = None
        if use_sealevel:
            try:
                work = merge_wave_and_sealevel(work, sealevel_norm, tolerance=sealevel_tolerance)
                eta_col = "sea-level signal [m]"
            except ValueError:
                # Could not align this source's timestamps with the sea-level series
                # within tolerance; fall back to a constant (zero) offset for this
                # source rather than dropping it entirely.
                eta_col = None

        for _, row in work.iterrows():
            eta_value = float(row[eta_col]) if eta_col else float(constant_eta)
            member = row[member_col] if member_col else None

            values = RunupInputs(
                hs=float(row["Hs [m]"]),
                tp=float(row["Tp [s]"]),
                slope=float(slope),
                swl=eta_value,
            )
            try:
                runup_results = compute_runup(values)
            except ValueError:
                # hs/tp <= 0 for this timestep (flat calm sea, or a rare spline
                # overshoot near zero) - skip just this one row/member rather than
                # aborting the entire forecast.
                skipped_count += 1
                continue

            for model_name, runup in runup_results.items():
                if not np.isfinite(runup):
                    continue

                model_id = (
                    f"{source_name}::{model_name}"
                    if member is None
                    else f"{source_name}::{member}::{model_name}"
                )

                rows.append(
                    {
                        "time": row["time"],
                        "Source": source_name,
                        "Member": member,
                        "Runup model": model_name,
                        "Model": model_id,
                        "Hs [m]": float(row["Hs [m]"]),
                        "Tp [s]": float(row["Tp [s]"]),
                        "Water level [m]": eta_value,
                        "Runup [m]": float(runup),
                        "Total water level [m]": float(runup + eta_value),
                    }
                )

    for source_name, df in source_wave_frames.items():
        _process(source_name, df)

    if noaa_detail_df is not None and not noaa_detail_df.empty:
        noaa_df = noaa_detail_df.rename(columns={"Model": "Member"})
        _process("NOAA GEFS-Wave", noaa_df, member_col="Member")

    return pd.DataFrame(rows), skipped_count


def build_runup_envelope(detail_df: pd.DataFrame) -> pd.DataFrame:
    """Per-timestamp min/mean/max of Runup and Total water level, combined across
    every source, ensemble member, and runup model present in detail_df."""
    if detail_df.empty:
        return pd.DataFrame()

    envelope_df = (
        detail_df.groupby("time")
        .agg(
            runup_min=("Runup [m]", "min"),
            runup_mean=("Runup [m]", "mean"),
            runup_max=("Runup [m]", "max"),
            twl_min=("Total water level [m]", "min"),
            twl_mean=("Total water level [m]", "mean"),
            twl_max=("Total water level [m]", "max"),
            n_estimates=("Runup [m]", "size"),
        )
        .reset_index()
    )
    return envelope_df
