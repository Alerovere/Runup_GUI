from io import BytesIO
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd


def fig_to_png_bytes(fig) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    buf.seek(0)
    return buf.getvalue()


def plot_profile_with_runup(
    profile_df: pd.DataFrame,
    results_df: pd.DataFrame,
    threshold: Optional[float] = None,
):
    import numpy as np
    import matplotlib.pyplot as plt

    profile = profile_df.copy().sort_values("x").reset_index(drop=True)

    x = profile["x"].to_numpy(dtype=float)
    y = profile["y"].to_numpy(dtype=float)

    if len(profile) < 2:
        raise ValueError("Profile must contain at least two points.")

    if "Total water level [m]" in results_df.columns:
        level_col = "Total water level [m]"
        title = "Beach profile and modelled total water levels"
    else:
        level_col = "Runup [m]"
        title = "Beach profile and modelled runup elevations"

    levels = results_df[level_col].to_numpy(dtype=float)
    mean_level = float(np.nanmean(levels))
    std_level = float(np.nanstd(levels, ddof=0))
    max_level = float(np.nanmax(levels))

    left_is_landward = y[0] >= y[-1]

    target_min = -2.0
    target_max = max(max_level + 0.5, float(np.nanmax(y)))
    if threshold is not None:
        target_max = max(target_max, float(threshold) + 0.5)

    x_sea_ext = None
    y_sea_ext = None
    x_land_ext = None
    y_land_ext = None

    if left_is_landward:
        if np.nanmin(y) > target_min:
            x1, y1 = x[-2], y[-2]
            x2, y2 = x[-1], y[-1]
            dx = x2 - x1
            dy = y2 - y1
            if dx != 0:
                slope = dy / dx
                if slope != 0:
                    x_ext = x2 + (target_min - y2) / slope
                    if np.isfinite(x_ext) and x_ext > x2:
                        x_sea_ext = np.array([x2, x_ext])
                        y_sea_ext = np.array([y2, target_min])

        if np.nanmax(y) < target_max:
            x1, y1 = x[1], y[1]
            x2, y2 = x[0], y[0]
            dx = x2 - x1
            dy = y2 - y1
            if dx != 0:
                slope = dy / dx
                if slope <= 0:
                    slope = -0.05
                x_ext = x2 + (target_max - y2) / slope
                if np.isfinite(x_ext) and x_ext < x2:
                    x_land_ext = np.array([x_ext, x2])
                    y_land_ext = np.array([target_max, y2])

    else:
        if np.nanmin(y) > target_min:
            x1, y1 = x[0], y[0]
            x2, y2 = x[1], y[1]
            dx = x2 - x1
            dy = y2 - y1
            if dx != 0:
                slope = dy / dx
                if slope != 0:
                    x_ext = x1 + (target_min - y1) / slope
                    if np.isfinite(x_ext) and x_ext < x1:
                        x_sea_ext = np.array([x_ext, x1])
                        y_sea_ext = np.array([target_min, y1])

        if np.nanmax(y) < target_max:
            x1, y1 = x[-2], y[-2]
            x2, y2 = x[-1], y[-1]
            dx = x2 - x1
            dy = y2 - y1
            if dx != 0:
                slope = dy / dx
                if slope <= 0:
                    slope = 0.05
                x_ext = x2 + (target_max - y2) / slope
                if np.isfinite(x_ext) and x_ext > x2:
                    x_land_ext = np.array([x2, x_ext])
                    y_land_ext = np.array([y2, target_max])

    x_full = x.copy()
    y_full = y.copy()

    if x_land_ext is not None:
        if left_is_landward:
            x_full = np.concatenate([x_land_ext[:-1], x_full])
            y_full = np.concatenate([y_land_ext[:-1], y_full])
        else:
            x_full = np.concatenate([x_full, x_land_ext[1:]])
            y_full = np.concatenate([y_full, y_land_ext[1:]])

    if x_sea_ext is not None:
        if left_is_landward:
            x_full = np.concatenate([x_full, x_sea_ext[1:]])
            y_full = np.concatenate([y_full, y_sea_ext[1:]])
        else:
            x_full = np.concatenate([x_sea_ext[:-1], x_full])
            y_full = np.concatenate([y_sea_ext[:-1], y_full])

    def find_intersection_x(level, xvals, yvals):
        intersections = []
        for i in range(len(xvals) - 1):
            xa, xb = xvals[i], xvals[i + 1]
            ya, yb = yvals[i], yvals[i + 1]

            if ya == level:
                intersections.append(xa)

            if (ya - level) * (yb - level) < 0:
                frac = (level - ya) / (yb - ya)
                xi = xa + frac * (xb - xa)
                intersections.append(xi)

            if yb == level:
                intersections.append(xb)

        if not intersections:
            return None

        return max(intersections) if left_is_landward else min(intersections)

    x_min = float(np.nanmin(x_full))
    x_max = float(np.nanmax(x_full))

    msl_intersection = find_intersection_x(0.0, x_full, y_full)
    mean_intersection = find_intersection_x(mean_level, x_full, y_full)
    upper_intersection = find_intersection_x(mean_level + std_level, x_full, y_full)
    lower_intersection = find_intersection_x(mean_level - std_level, x_full, y_full)

    fig, ax = plt.subplots(figsize=(5.2, 3.8), dpi=160)

    ax.plot(x, y, color="black", linewidth=1.8, label="Shoreline/profile")

    extension_labeled = False
    if x_sea_ext is not None and y_sea_ext is not None:
        ax.plot(
            x_sea_ext,
            y_sea_ext,
            color="black",
            linewidth=1.2,
            linestyle=":",
            label="Theoretical beach profile extension",
        )
        extension_labeled = True

    if x_land_ext is not None and y_land_ext is not None:
        ax.plot(
            x_land_ext,
            y_land_ext,
            color="black",
            linewidth=1.2,
            linestyle=":",
            label=None if extension_labeled else "Theoretical beach profile extension",
        )

    if msl_intersection is not None:
        if left_is_landward:
            ax.hlines(
                0.0,
                msl_intersection,
                x_max,
                colors="royalblue",
                linewidth=1.4,
                label="Mean sea level",
            )
            ax.text(x_max, 0.0, "  MSL", color="royalblue", va="center", ha="left", fontsize=8)
        else:
            ax.hlines(
                0.0,
                x_min,
                msl_intersection,
                colors="royalblue",
                linewidth=1.4,
                label="Mean sea level",
            )
            ax.text(x_min, 0.0, "MSL  ", color="royalblue", va="center", ha="right", fontsize=8)

    single_model_labeled = False
    for _, row in results_df.iterrows():
        level = float(row[level_col])
        xi = find_intersection_x(level, x_full, y_full)
        if xi is not None:
            if left_is_landward:
                ax.hlines(
                    level,
                    xi,
                    x_max,
                    colors="lightgray",
                    linewidth=1.0,
                    alpha=0.9,
                    linestyles=":",
                    label="Single model outputs" if not single_model_labeled else None,
                )
            else:
                ax.hlines(
                    level,
                    x_min,
                    xi,
                    colors="lightgray",
                    linewidth=1.0,
                    alpha=0.9,
                    linestyles=":",
                    label="Single model outputs" if not single_model_labeled else None,
                )
            single_model_labeled = True

    if std_level > 0 and upper_intersection is not None and lower_intersection is not None:
        if left_is_landward:
            x_poly = [upper_intersection, x_max, x_max, lower_intersection]
        else:
            x_poly = [x_min, upper_intersection, lower_intersection, x_min]

        y_poly = [
            mean_level + std_level,
            mean_level + std_level,
            mean_level - std_level,
            mean_level - std_level,
        ]

        ax.fill(
            x_poly,
            y_poly,
            color="lightsteelblue",
            alpha=0.45,
            edgecolor="none",
            label="Mean ± 1 SD",
        )

    if mean_intersection is not None:
        if left_is_landward:
            ax.hlines(
                mean_level,
                mean_intersection,
                x_max,
                colors="darkblue",
                linewidth=1.8,
                label="Model mean",
            )
        else:
            ax.hlines(
                mean_level,
                x_min,
                mean_intersection,
                colors="darkblue",
                linewidth=1.8,
                label="Model mean",
            )

    if threshold is not None:
        threshold_intersection = find_intersection_x(float(threshold), x_full, y_full)
        if threshold_intersection is not None:
            if left_is_landward:
                ax.hlines(
                    float(threshold),
                    threshold_intersection,
                    x_max,
                    colors="crimson",
                    linewidth=1.4,
                    linestyles="--",
                    label="Critical elevation threshold",
                )
            else:
                ax.hlines(
                    float(threshold),
                    x_min,
                    threshold_intersection,
                    colors="crimson",
                    linewidth=1.4,
                    linestyles="--",
                    label="Critical elevation threshold",
                )

    ax.set_xlim(x_min, x_max)
    ax.set_xlabel("Cross-shore distance x [m]", fontsize=9)
    ax.set_ylabel("Elevation y [m]", fontsize=9)
    ax.set_title(title, fontsize=10, pad=8)

    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)

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


def plot_runup_twl_comparison(
    results_df: pd.DataFrame,
    threshold: Optional[float] = None,
    risk_color: Optional[str] = None,
    risk_label: Optional[str] = None,
):
    plot_df = results_df.copy()

    sort_col = "Total water level [m]" if "Total water level [m]" in plot_df.columns else "Runup [m]"
    plot_df = plot_df.sort_values(sort_col, ascending=True).reset_index(drop=True)
    plot_df["Short model"] = [name.replace(" et al.", "") for name in plot_df["Model"]]

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
        compare_col = "Total water level [m]"
    else:
        title = "Runup"
        compare_col = "Runup [m]"

    if threshold is not None:
        ax.axvline(
            float(threshold),
            color="crimson",
            linestyle="--",
            linewidth=1.4,
            label="Critical elevation threshold",
        )

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

    if risk_color is not None and risk_label is not None:
        ax.text(
            0.99,
            1.02,
            risk_label,
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            color="white",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=risk_color, edgecolor="none"),
        )

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
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(7.2, 5.6),
        dpi=160,
        sharex=True,
    )

    time = pd.to_datetime(envelope_df["time"])

    # Significant wave height
    axes[0].plot(time, envelope_df["hs_mean"], color="skyblue", linewidth=2)
    axes[0].set_ylabel("Hs [m]", fontsize=9)
    axes[0].set_title("Wave and water-level forcing", fontsize=10, pad=8)

    # Peak period
    axes[1].plot(time, envelope_df["tp_mean"], color="goldenrod", linewidth=2)
    axes[1].set_ylabel("Tp [s]", fontsize=9)

    # Water level
    axes[2].plot(time, envelope_df["wl_mean"], color="cornflowerblue", linewidth=2)
    axes[2].set_ylabel("WL [m]", fontsize=9)

    # Shared styling
    for ax in axes:
        ax.tick_params(axis="y", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(False)

    # Date formatting: Apr 4, Apr 5, ...
    axes[2].xaxis.set_major_locator(mdates.DayLocator())
    try:
        axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    except ValueError:
        # Fallback for systems that do not support %-d
        axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    axes[2].tick_params(axis="x", labelsize=8, rotation=0)
    axes[2].set_xlabel("Date", fontsize=9)

    fig.tight_layout()
    return fig


def plot_daily_threshold_bar(daily_status_df: pd.DataFrame, title: str = "Daily threshold status"):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.0, 1.8), dpi=160)

    for i, row in daily_status_df.iterrows():
        ax.bar(
            i,
            1,
            color=row["color"],
            width=0.95,
            edgecolor="white",
            linewidth=1.0,
        )

    ax.set_xlim(-0.5, len(daily_status_df) - 0.5)
    ax.set_ylim(0, 1)
    ax.set_yticks([])

    labels = [
        pd.to_datetime(str(d)).strftime("%a\n%d %b")
        for d in daily_status_df["date"]
    ]
    ax.set_xticks(range(len(daily_status_df)))
    ax.set_xticklabels(labels, fontsize=8)

    ax.set_title(title, fontsize=10, pad=8)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    for i, row in daily_status_df.iterrows():
        ax.text(
            i,
            0.5,
            row["label"][0],
            ha="center",
            va="center",
            fontsize=8,
            color="white",
            fontweight="bold",
        )

    fig.tight_layout()
    return fig