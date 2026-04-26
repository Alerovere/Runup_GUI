from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

def plot_profile_with_runup(profile_df: pd.DataFrame, results_df: pd.DataFrame):
    import numpy as np
    import matplotlib.pyplot as plt

    profile = profile_df.copy().sort_values("x").reset_index(drop=True)

    x = profile["x"].to_numpy(dtype=float)
    y = profile["y"].to_numpy(dtype=float)

    target_min = -2.0

    # Seaward/downward extension from first two points if profile does not reach -2 m
    x_sea_ext = None
    y_sea_ext = None
    if np.nanmin(y) > target_min and len(profile) >= 2:
        x1, y1 = x[0], y[0]
        x2, y2 = x[1], y[1]
        if x2 != x1 and y2 != y1:
            slope = (y2 - y1) / (x2 - x1)
            if slope != 0:
                x_ext = x1 + (target_min - y1) / slope
                if np.isfinite(x_ext) and x_ext < x1:
                    x_sea_ext = np.array([x_ext, x1])
                    y_sea_ext = np.array([target_min, y1])

    # Landward/upward extension from last two points if profile is not high enough
    max_level = float(np.nanmax(
        results_df["Total water level [m]"].to_numpy(dtype=float)
        if "Total water level [m]" in results_df.columns
        else results_df["Runup [m]"].to_numpy(dtype=float)
    ))
    target_max = max(max_level + 0.5, float(np.nanmax(y)))

    x_land_ext = None
    y_land_ext = None
    if np.nanmax(y) < target_max and len(profile) >= 2:
        x1, y1 = x[-2], y[-2]
        x2, y2 = x[-1], y[-1]
        if x2 != x1 and y2 != y1:
            slope = (y2 - y1) / (x2 - x1)
            if slope != 0:
                x_ext = x2 + (target_max - y2) / slope
                if np.isfinite(x_ext) and x_ext > x2:
                    x_land_ext = np.array([x2, x_ext])
                    y_land_ext = np.array([y2, target_max])

    # Build extended profile for intersections
    x_full = x.copy()
    y_full = y.copy()

    if x_sea_ext is not None:
        x_full = np.concatenate([x_sea_ext[:-1], x_full])
        y_full = np.concatenate([y_sea_ext[:-1], y_full])

    if x_land_ext is not None:
        x_full = np.concatenate([x_full, x_land_ext[1:]])
        y_full = np.concatenate([y_full, y_land_ext[1:]])

    def find_intersection_x(level, xvals, yvals):
        intersections = []
        for i in range(len(xvals) - 1):
            x1, x2 = xvals[i], xvals[i + 1]
            y1, y2 = yvals[i], yvals[i + 1]

            if (y1 - level) == 0:
                intersections.append(x1)

            if (y1 - level) * (y2 - level) < 0:
                frac = (level - y1) / (y2 - y1)
                xi = x1 + frac * (x2 - x1)
                intersections.append(xi)

            if (y2 - level) == 0:
                intersections.append(x2)

        if not intersections:
            return None

        return max(intersections)

    if "Total water level [m]" in results_df.columns:
        level_col = "Total water level [m]"
        title = "Beach profile and modelled total water levels"
    else:
        level_col = "Runup [m]"
        title = "Beach profile and modelled runup elevations"

    levels = results_df[level_col].to_numpy(dtype=float)
    mean_level = float(np.nanmean(levels))
    std_level = float(np.nanstd(levels, ddof=0))

    x_max = float(np.nanmax(x_full))
    x_min = float(np.nanmin(x_full))

    msl_intersection = find_intersection_x(0.0, x_full, y_full)
    mean_intersection = find_intersection_x(mean_level, x_full, y_full)
    upper_intersection = find_intersection_x(mean_level + std_level, x_full, y_full)
    lower_intersection = find_intersection_x(mean_level - std_level, x_full, y_full)

    fig, ax = plt.subplots(figsize=(5.2, 3.8), dpi=160)

    # Original profile
    ax.plot(x, y, color="black", linewidth=1.8, label="Shoreline/profile")

    # Seaward extension
    if x_sea_ext is not None and y_sea_ext is not None:
        ax.plot(x_sea_ext, y_sea_ext, color="black", linewidth=1.2, linestyle=":")

    # Landward extension
    if x_land_ext is not None and y_land_ext is not None:
        ax.plot(x_land_ext, y_land_ext, color="black", linewidth=1.2, linestyle=":")

    # Mean sea level
    ax.hlines(
        0.0,
        x_min,
        x_max,
        colors="royalblue",
        linewidth=1.4,
        label="Mean sea level",
    )
        ax.text(
            x_max,
            0.0,
            "  MSL",
            color="royalblue",
            va="center",
            ha="left",
            fontsize=8,
        )

    # Individual model lines
    for _, row in results_df.iterrows():
        level = float(row[level_col])
        xi = find_intersection_x(level, x_full, y_full)
        if xi is not None:
            ax.hlines(
                level,
                xi,
                x_max,
                colors="lightgray",
                linewidth=1.0,
                alpha=0.9,
            )

    # Mean ± 1 SD band
    if std_level > 0 and upper_intersection is not None and lower_intersection is not None:
        band_start = max(upper_intersection, lower_intersection)
        xx = np.linspace(band_start, x_max, 200)
        ax.fill_between(
            xx,
            mean_level - std_level,
            mean_level + std_level,
            color="lightsteelblue",
            alpha=0.5,
            label="Mean ± 1 SD",
        )

    # Mean level line
    if mean_intersection is not None:
        ax.hlines(
            mean_level,
            mean_intersection,
            x_max,
            colors="dimgray",
            linewidth=1.6,
            label="Model mean",
        )

    ax.set_xlim(x_min, x_max)
    ax.set_xlabel("Cross-shore distance x [m]", fontsize=9)
    ax.set_ylabel("Elevation y [m]", fontsize=9)
    ax.set_title(title, fontsize=10, pad=8)

    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(True, alpha=0.2, linewidth=0.8)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(
        frameon=False,
        fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=2,
        handlelength=1.6,
        columnspacing=1.4,
    )

    fig.tight_layout()
    return fig


def plot_runup_twl_comparison(results_df: pd.DataFrame):
    plot_df = results_df.copy()

    if "Total water level [m]" in plot_df.columns:
        plot_df = plot_df.sort_values("Total water level [m]", ascending=True).reset_index(drop=True)
    else:
        plot_df = plot_df.sort_values("Runup [m]", ascending=True).reset_index(drop=True)

    plot_df["Short model"] = [
        name.replace(" et al.", "")
        for name in plot_df["Model"]
    ]

    fig, ax = plt.subplots(figsize=(5.2, 3.8), dpi=160)

    y = range(len(plot_df))

    ax.barh(
        y,
        plot_df["Runup [m]"],
        height=0.5,
        edgecolor="none",
        label="Runup",
    )

    if "Total water level [m]" in plot_df.columns:
        twl_extension = plot_df["Total water level [m]"] - plot_df["Runup [m]"]
        ax.barh(
            y,
            twl_extension,
            left=plot_df["Runup [m]"],
            height=0.5,
            edgecolor="none",
            alpha=0.5,
            color="lightblue",
            label="TWL addition",
        )
        title = "Runup and total water level"
    else:
        title = "Runup"

    ax.set_yticks(list(y))
    ax.set_yticklabels(plot_df["Short model"], fontsize=8)
    ax.set_xlabel("Elevation [m]", fontsize=9)
    ax.set_ylabel("Model", fontsize=9)
    ax.set_title(title, fontsize=10, pad=8)

    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)

    ax.grid(True, axis="x", alpha=0.2, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    if "Total water level [m]" in plot_df.columns:
        ax.legend(
            frameon=False,
            fontsize=8,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.18),
            ncol=2,
            handlelength=1.6,
            columnspacing=1.4,
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