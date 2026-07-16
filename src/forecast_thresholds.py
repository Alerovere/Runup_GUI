from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd


SEVERITY_MAP = {
    "green": 0,
    "yellow": 1,
    "orange": 2,
    "red": 3,
}

REVERSE_SEVERITY_MAP = {v: k for k, v in SEVERITY_MAP.items()}

COLOR_MAP = {
    "green": "green",
    "yellow": "#d8b400",
    "orange": "orange",
    "red": "red",
}

LABEL_MAP = {
    "green": "GREEN",
    "yellow": "YELLOW",
    "orange": "ORANGE",
    "red": "RED",
}


def classify_threshold_at_timestep(
    threshold: float,
    mean_val: float,
    sd_val: float,
    max_val: float,
) -> str:
    if threshold > max_val:
        return "green"
    if threshold > mean_val + sd_val:
        return "yellow"
    if threshold > mean_val - sd_val:
        return "orange"
    return "red"


def build_threshold_timeseries(detail_df: pd.DataFrame, value_col: str, threshold: float) -> pd.DataFrame:
    grouped = (
        detail_df.groupby("time")
        .agg(
            mean_val=(value_col, "mean"),
            sd_val=(value_col, "std"),
            max_val=(value_col, "max"),
        )
        .reset_index()
    )

    grouped["sd_val"] = grouped["sd_val"].fillna(0.0)

    grouped["status"] = grouped.apply(
        lambda row: classify_threshold_at_timestep(
            threshold=float(threshold),
            mean_val=float(row["mean_val"]),
            sd_val=float(row["sd_val"]),
            max_val=float(row["max_val"]),
        ),
        axis=1,
    )

    grouped["severity"] = grouped["status"].map(SEVERITY_MAP)
    grouped["date"] = pd.to_datetime(grouped["time"]).dt.date
    return grouped


def build_daily_threshold_status(status_df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        status_df.groupby("date")
        .agg(
            severity=("severity", "max"),
        )
        .reset_index()
    )
    daily["status"] = daily["severity"].map(REVERSE_SEVERITY_MAP)
    daily["color"] = daily["status"].map(COLOR_MAP)
    daily["label"] = daily["status"].map(LABEL_MAP)
    return daily


def summarize_threshold_status(status_df: pd.DataFrame) -> Dict[str, object]:
    worst_severity = int(status_df["severity"].max())
    worst_status = REVERSE_SEVERITY_MAP[worst_severity]

    exceed_df = status_df[status_df["status"] != "green"]
    first_exceedance = None
    if not exceed_df.empty:
        first_exceedance = pd.to_datetime(exceed_df["time"].min())

    counts = status_df["status"].value_counts().to_dict()

    return {
        "worst_status": worst_status,
        "worst_color": COLOR_MAP[worst_status],
        "worst_label": LABEL_MAP[worst_status],
        "first_exceedance": first_exceedance,
        "counts": counts,
    }


def build_exceedance_events(status_df: pd.DataFrame) -> pd.DataFrame:
    """Group consecutive non-green timesteps into discrete exceedance events, each
    reporting the start time, end time, and worst status reached during that run.
    This answers "when" the threshold gets surpassed, rather than just whether it does."""
    df = status_df.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])

    is_exceed = df["status"] != "green"
    run_id = (is_exceed != is_exceed.shift(fill_value=False)).cumsum()

    events = []
    for rid, group in df.groupby(run_id):
        if not (group["status"] != "green").iloc[0]:
            continue
        worst_severity = int(group["severity"].max())
        worst_status = REVERSE_SEVERITY_MAP[worst_severity]
        events.append(
            {
                "Start": group["time"].min(),
                "End": group["time"].max(),
                "Worst status": LABEL_MAP[worst_status],
            }
        )

    return pd.DataFrame(events)


def describe_threshold_logic(compare_label: str, threshold: float) -> str:
    return f"""
**Threshold interpretation**  
The critical threshold is evaluated against forecast **{compare_label}**.

- **Green** = threshold above all model outputs  
- **Yellow** = threshold exceeded by some individual models only  
- **Orange** = threshold lies within the mean ± 1 SD model range  
- **Red** = threshold below mean - 1 SD, indicating robust exceedance

Threshold used: **{threshold:.2f} m**
""".strip()


def describe_worst_status(worst_status: str, threshold: float, compare_label: str) -> str:
    if worst_status == "green":
        return f"The threshold ({threshold:.2f} m) remains above all forecast {compare_label} outputs."
    if worst_status == "yellow":
        return f"The threshold ({threshold:.2f} m) is exceeded by some individual forecast {compare_label} model outputs."
    if worst_status == "orange":
        return f"The threshold ({threshold:.2f} m) falls within the forecast {compare_label} mean ± 1 SD range."
    return f"The threshold ({threshold:.2f} m) is below the forecast {compare_label} mean - 1 SD level, indicating robust exceedance."