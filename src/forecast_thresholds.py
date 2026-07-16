from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# Probability bands used to translate a raw exceedance probability into a
# simple, at-a-glance category. Upper bound is exclusive of the category above
# it (e.g. exactly 0.10 falls in "Moderate", not "Low").
EXCEEDANCE_CATEGORIES: List[Tuple[float, str, str]] = [
    (0.10, "Low", "#2ca25f"),
    (0.40, "Moderate", "#d8b400"),
    (0.70, "High", "#e6550d"),
    (1.01, "Critical", "#cb181d"),
]


def categorize_probability(probability: float) -> Tuple[str, str]:
    """Map a 0-1 exceedance probability to (category label, color)."""
    for upper, label, color in EXCEEDANCE_CATEGORIES:
        if probability < upper:
            return label, color
    return EXCEEDANCE_CATEGORIES[-1][1], EXCEEDANCE_CATEGORIES[-1][2]


def build_source_exceedance_probability(
    detail_df: pd.DataFrame,
    value_col: str,
    threshold: float,
) -> pd.DataFrame:
    """Per-timestep, per-source fraction of estimates exceeding the threshold.

    detail_df is expected to have a "Source" column (as produced by
    src.runup_forecast.compute_multi_source_runup_detail), so that each
    source's own runup-model spread (and, for NOAA, ensemble-member spread)
    is summarized on its own before being combined across sources.
    """
    df = detail_df.copy()
    df["time"] = pd.to_datetime(df["time"])
    df["exceeds"] = df[value_col] > float(threshold)

    grouped = (
        df.groupby(["time", "Source"])["exceeds"]
        .agg(n_exceed="sum", n_total="count")
        .reset_index()
    )
    grouped["source_probability"] = grouped["n_exceed"] / grouped["n_total"]
    return grouped


def build_exceedance_probability_timeseries(
    detail_df: pd.DataFrame,
    value_col: str,
    threshold: float,
) -> pd.DataFrame:
    """Per-timestep exceedance probability, weighted equally across sources.

    NOAA contributes far more individual estimates per timestep than
    Copernicus or Open-Meteo (31 members x ~10 runup models, vs ~10 each for
    the other two single-series sources). Pooling every estimate unweighted
    would let NOAA's sheer volume dominate the number. Instead, the exceedance
    probability is computed separately per source, then averaged with equal
    weight across the sources that are actually present - each independent
    forecast source gets an equal vote, regardless of how many
    models/members feed into it.
    """
    per_source = build_source_exceedance_probability(detail_df, value_col, threshold)

    ts = (
        per_source.groupby("time")["source_probability"]
        .mean()
        .reset_index()
        .rename(columns={"source_probability": "probability"})
        .sort_values("time")
        .reset_index(drop=True)
    )
    ts["date"] = pd.to_datetime(ts["time"]).dt.date

    categorized = ts["probability"].apply(categorize_probability)
    ts["category"] = categorized.apply(lambda t: t[0])
    ts["color"] = categorized.apply(lambda t: t[1])
    return ts


def build_daily_exceedance_probability(prob_ts_df: pd.DataFrame) -> pd.DataFrame:
    """Daily summary: the worst (peak) exceedance probability reached each day."""
    daily = prob_ts_df.groupby("date")["probability"].max().reset_index()
    categorized = daily["probability"].apply(categorize_probability)
    daily["category"] = categorized.apply(lambda t: t[0])
    daily["color"] = categorized.apply(lambda t: t[1])
    return daily


def summarize_exceedance_probability(prob_ts_df: pd.DataFrame, alert_probability: float = 0.5) -> Dict[str, object]:
    worst_idx = prob_ts_df["probability"].idxmax()
    worst_row = prob_ts_df.loc[worst_idx]

    alert_df = prob_ts_df[prob_ts_df["probability"] >= alert_probability]
    first_alert = None
    if not alert_df.empty:
        first_alert = pd.to_datetime(alert_df["time"].min())

    return {
        "worst_probability": float(worst_row["probability"]),
        "worst_category": worst_row["category"],
        "worst_color": worst_row["color"],
        "worst_time": pd.to_datetime(worst_row["time"]),
        "first_alert_time": first_alert,
        "alert_probability": alert_probability,
    }


def build_exceedance_events(prob_ts_df: pd.DataFrame, alert_probability: float = 0.5) -> pd.DataFrame:
    """Group consecutive timesteps where the exceedance probability is at or
    above alert_probability into discrete events, each reporting the start
    time, end time, and peak probability reached. This answers "when" the
    threshold becomes a real concern, not just whether it ever does."""
    df = prob_ts_df.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])

    is_alert = df["probability"] >= alert_probability
    run_id = (is_alert != is_alert.shift(fill_value=False)).cumsum()

    events = []
    for _, group in df.groupby(run_id):
        if not (group["probability"] >= alert_probability).iloc[0]:
            continue
        peak_probability = float(group["probability"].max())
        events.append(
            {
                "Start": group["time"].min(),
                "End": group["time"].max(),
                "Peak probability": f"{peak_probability:.0%}",
                "Category": categorize_probability(peak_probability)[0],
            }
        )

    return pd.DataFrame(events)


def describe_exceedance_methodology(compare_label: str, threshold: float) -> str:
    return f"""
**How this probability is calculated**

At every forecast timestep, each selected source (Copernicus, Open-Meteo, NOAA GEFS-Wave) contributes a set of
independent {compare_label} estimates - one per empirical runup model, and for NOAA, one per ensemble member as well.
The exceedance probability is the fraction of each source's own estimates above the threshold, averaged with equal
weight across the sources that are present, so a source with many models/members (NOAA) doesn't dominate one with a
single deterministic series (Copernicus, Open-Meteo).

Threshold used: **{threshold:.2f} m**, evaluated against forecast **{compare_label}**.

This is an empirical, model-based probability - a measure of agreement/disagreement across the available forecast
sources and empirical runup formulas - not a rigorously calibrated statistical forecast probability.
""".strip()


def describe_worst_probability(worst_probability: float, worst_category: str, threshold: float, compare_label: str) -> str:
    return (
        f"Peak exceedance probability in this forecast: **{worst_probability:.0%}** ({worst_category}) that "
        f"forecast {compare_label} exceeds {threshold:.2f} m."
    )
