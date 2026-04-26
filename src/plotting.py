from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd


def plot_profile_with_runup(profile_df: pd.DataFrame, results_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(profile_df["x"], profile_df["y"], label="Beach profile")

    x_min = float(profile_df["x"].min())
    x_max = float(profile_df["x"].max())

    for _, row in results_df.iterrows():
        ax.hlines(
            float(row["Total water level [m]"]),
            x_min,
            x_max,
            linestyles="--",
            label=row["Model"],
        )

    ax.set_xlabel("Cross-shore distance x [m]")
    ax.set_ylabel("Elevation y [m]")
    ax.set_title("Beach profile with modelled total water levels")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    return fig


def plot_barh(df: pd.DataFrame, category_col: str, value_col: str, title: str, xlabel: str):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(df[category_col], df[value_col])
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(category_col)
    ax.grid(True, axis="x", alpha=0.3)
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