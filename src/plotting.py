from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd


def plot_profile_with_runup(profile_df: pd.DataFrame, results_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(6.2, 3.8))

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
            linewidth=1.0,
            label=row["Model"],
        )

    ax.set_xlabel("Cross-shore distance x [m]", fontsize=9)
    ax.set_ylabel("Elevation y [m]", fontsize=9)
    ax.set_title(title, fontsize=10, pad=8)
    ax.grid(True, alpha=0.25, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.tight_layout()
    return fig


def plot_runup_twl_comparison(results_df: pd.DataFrame):
    plot_df = results_df.copy()
    plot_df["Short model"] = [
        name.replace(" et al.", "").replace(" (", "\n(")
        for name in plot_df["Model"]
    ]

    fig, ax = plt.subplots(figsize=(5.8, 2.8))

    y = range(len(plot_df))

    ax.barh(
        y,
        plot_df["Runup [m]"],
        height=0.42,
        edgecolor="none",
        label="Runup",
    )

    if "Total water level [m]" in plot_df.columns:
        ax.scatter(
            plot_df["Total water level [m]"],
            y,
            marker="o",
            s=28,
            zorder=3,
            label="TWL",
        )
        title = "Runup and total water level"
    else:
        title = "Runup"

    ax.set_yticks(list(y))
    ax.set_yticklabels(plot_df["Short model"], fontsize=7.5)
    ax.set_xlabel("Elevation [m]", fontsize=9)
    ax.set_ylabel("")
    ax.set_title(title, fontsize=10, pad=8)

    ax.grid(True, axis="x", alpha=0.2, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if "Total water level [m]" in plot_df.columns:
        ax.legend(
            frameon=False,
            fontsize=8,
            loc="lower right",
            handlelength=1.2,
        )

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