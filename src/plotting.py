from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd


def plot_profile_with_runup(profile_df: pd.DataFrame, results_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(7.2, 4.2))

    ax.plot(
        profile_df["x"],
        profile_df["y"],
        linewidth=2,
        label="Beach profile",
    )

    x_min = float(profile_df["x"].min())
    x_max = float(profile_df["x"].max())

    if "Total water level [m]" in results_df.columns:
        level_col = "Total water level [m]"
        title = "Beach profile with modelled total water levels"
    else:
        level_col = "Runup [m]"
        title = "Beach profile with modelled runup elevations"

    for _, row in results_df.iterrows():
        ax.hlines(
            float(row[level_col]),
            x_min,
            x_max,
            linestyles="--",
            linewidth=1.2,
            label=row["Model"],
        )

    ax.set_xlabel("Cross-shore distance x [m]")
    ax.set_ylabel("Elevation y [m]")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    return fig


def plot_runup_twl_comparison(results_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(6.8, 3.8))

    y = range(len(results_df))

    ax.barh(
        y,
        results_df["Runup [m]"],
        height=0.55,
        label="Runup [m]",
    )

    if "Total water level [m]" in results_df.columns:
        ax.scatter(
            results_df["Total water level [m]"],
            y,
            marker="o",
            s=45,
            label="Total water level [m]",
            zorder=3,
        )
        title = "Runup and total water level across models"
    else:
        title = "Runup across models"

    ax.set_yticks(list(y))
    ax.set_yticklabels(results_df["Model"])
    ax.set_xlabel("Elevation [m]")
    ax.set_ylabel("Model")
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_envelope(envelope_df: pd.DataFrame, threshold: Optional[float], mode: str):
    fig, ax = plt.subplots(figsize=(10, 5))

    if mode == "runup":
        low = envelope_df["runup_min"]
        mid = envelope_df["runup_mean"]
        high = envelope_df["runup_max"]
        ylabel = "Runup [m]"
        title = "Weekly runup envelope across models"
    else:
        low = envelope_df["twl_min"]
        mid = envelope_df["twl_mean"]
        high = envelope_df["twl_max"]
        ylabel = "Total water level [m]"
        title = "Weekly total water level envelope across models"

    ax.fill_between(envelope_df["time"], low, high, alpha=0.25, label="Model range")
    ax.plot(envelope_df["time"], mid, linewidth=2, label="Model mean")

    if threshold is not None:
        ax.axhline(threshold, linestyle="--", linewidth=1.5, label="Threshold elevation")

    ax.set_title(title)
    ax.set_xlabel("Time")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    return fig


def plot_wave_timeseries(envelope_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(envelope_df["time"], envelope_df["hs_mean"], label="Hs [m]")
    ax.plot(envelope_df["time"], envelope_df["tp_mean"], label="Tp [s]")
    ax.set_title("Forecast wave conditions at selected point")
    ax.set_xlabel("Time")
    ax.set_ylabel("Value")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    return fig