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

    x_raw = profile["x"].to_numpy(dtype=float)
    y_raw = profile["y"].to_numpy(dtype=float)

    if len(profile) < 2:
        raise ValueError("Profile must contain at least two points.")

    # -------------------------------------------------
    # 1. Always orient profile so that seaward is right
    # -------------------------------------------------
    # Heuristic: the side closest to the minimum elevation is assumed seaward.
    idx_min = int(np.argmin(y_raw))
    flip_profile = idx_min < len(y_raw) / 2

    if flip_profile:
        x_mirror = x_raw.min() + x_raw.max() - x_raw
        x = x_mirror
        y = y_raw.copy()

        sort_idx = np.argsort(x)
        x = x[sort_idx]
        y = y[sort_idx]
    else:
        x = x_raw.copy()
        y = y_raw.copy()

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

    # -------------------------------------------------
    # 2. Plot limits
    # -------------------------------------------------
    target_min = min(-2.0, float(np.nanmin(y)))
    target_max = max(float(np.nanmax(y)), max_level + 0.5)
    if threshold is not None:
        target_max = max(target_max, float(threshold) + 0.5)

    # -------------------------------------------------
    # 3. Extend ONLY offshore (to the right) if needed
    # -------------------------------------------------
    x_ext_sea = None
    y_ext_sea = None

    if np.nanmin(y) > target_min:
        x1, y1 = x[-2], y[-2]
        x2, y2 = x[-1], y[-1]
        dx = x2 - x1
        dy = y2 - y1

        if dx != 0:
            slope = dy / dx

            # Force offshore continuation to slope downward
            if slope >= 0:
                slope = -0.05 if slope == 0 else -abs(slope)

            x_to_target = x2 + (target_min - y2) / slope

            if np.isfinite(x_to_target) and x_to_target > x2:
                x_ext_sea = np.array([x2, x_to_target])
                y_ext_sea = np.array([y2, target_min])

    x_full = x.copy()
    y_full = y.copy()

    if x_ext_sea is not None:
        x_full = np.concatenate([x_full, x_ext_sea[1:]])
        y_full = np.concatenate([y_full, y_ext_sea[1:]])

    x_min = float(np.nanmin(x_full))
    x_max = float(np.nanmax(x_full))

    # -------------------------------------------------
    # 4. Intersections
    # -------------------------------------------------
    def find_intersections(level, xvals, yvals):
        xs = []

        for i in range(len(xvals) - 1):
            xa, xb = xvals[i], xvals[i + 1]
            ya, yb = yvals[i], yvals[i + 1]

            if ya == level:
                xs.append(xa)

            if (ya - level) * (yb - level) < 0:
                frac = (level - ya) / (yb - ya)
                xi = xa + frac * (xb - xa)
                xs.append(xi)

            if yb == level:
                xs.append(xb)

        if not xs:
            return []

        return sorted(set(float(v) for v in xs))

    # For runup/TWL-related quantities, use the most landward intersection.
    # If no intersection exists, continue to the left plot boundary.
    def landward_intersection_or_edge(level):
        xs = find_intersections(level, x_full, y_full)
        return min(xs) if xs else x_min

    # For MSL, use the shoreline intersection, i.e. the most seaward one.
    def shoreline_intersection_or_edge(level):
        xs = find_intersections(level, x_full, y_full)
        return max(xs) if xs else x_min

    mean_left = landward_intersection_or_edge(mean_level)
    upper_left = landward_intersection_or_edge(mean_level + std_level)
    lower_left = landward_intersection_or_edge(mean_level - std_level)
    msl_start = shoreline_intersection_or_edge(0.0)

    # Shared left boundary for model spread
    if std_level > 0:
        band_left = min(upper_left, lower_left)
    else:
        band_left = mean_left

    fig, ax = plt.subplots(figsize=(5.2, 3.8), dpi=160)

    # -------------------------------------------------
    # 5. Plot profile
    # -------------------------------------------------
    ax.plot(x, y, color="black", linewidth=1.8, label="Shoreline/profile")

    if x_ext_sea is not None and y_ext_sea is not None:
        ax.plot(
            x_ext_sea,
            y_ext_sea,
            color="black",
            linewidth=1.2,
            linestyle=":",
            label="Theoretical beach profile extension",
        )

    # Mean sea level
    ax.hlines(
        0.0,
        msl_start,
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

    # Single model outputs
    single_model_labeled = False
    for _, row in results_df.iterrows():
        level = float(row[level_col])
        x_left = landward_intersection_or_edge(level)
        x_left = min(x_left, band_left)

        ax.hlines(
            level,
            x_left,
            x_max,
            colors="lightgray",
            linewidth=1.0,
            alpha=0.9,
            linestyles=":",
            label="Single model outputs" if not single_model_labeled else None,
        )
        single_model_labeled = True

    # Mean ± 1 SD band
    if std_level > 0:
        ax.fill_between(
            [band_left, x_max],
            [mean_level - std_level, mean_level - std_level],
            [mean_level + std_level, mean_level + std_level],
            color="lightsteelblue",
            alpha=0.45,
            edgecolor="none",
            label="Mean ± 1 SD",
        )

    # Mean line
    ax.hlines(
        mean_level,
        band_left,
        x_max,
        colors="darkblue",
        linewidth=1.8,
        label="Model mean",
    )

    # Threshold
    if threshold is not None:
        threshold_left = landward_intersection_or_edge(float(threshold))
        threshold_left = min(threshold_left, band_left)

        ax.hlines(
            float(threshold),
            threshold_left,
            x_max,
            colors="crimson",
            linewidth=1.4,
            linestyles="--",
            label="Critical elevation threshold",
        )

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(target_min - 0.5, target_max + 0.5)
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


def plot_forecast_model_timeseries(
    detail_df: pd.DataFrame,
    value_col: str,
    threshold: float | None = None,
    title: str | None = None,
):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import pandas as pd

    df = detail_df.copy()
    df["time"] = pd.to_datetime(df["time"])

    pivot_df = df.pivot(index="time", columns="Model", values=value_col).sort_index()

    mean_series = pivot_df.mean(axis=1)
    std_series = pivot_df.std(axis=1).fillna(0.0)

    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=160)

    # Single model outputs
    for model in pivot_df.columns:
        ax.plot(
            pivot_df.index,
            pivot_df[model],
            color="lightgray",
            linestyle=":",
            linewidth=1.0,
            alpha=0.9,
        )

    # Standard deviation envelope
    ax.fill_between(
        pivot_df.index,
        mean_series - std_series,
        mean_series + std_series,
        color="lightsteelblue",
        alpha=0.45,
        edgecolor="none",
        label="Mean ± 1 SD",
    )

    # Mean line
    ax.plot(
        pivot_df.index,
        mean_series,
        color="darkblue",
        linewidth=2.0,
        label="Model mean",
    )

    # Threshold
    if threshold is not None:
        ax.axhline(
            float(threshold),
            color="crimson",
            linestyle="--",
            linewidth=1.4,
            label="Critical elevation threshold",
        )

    if title is None:
        title = value_col

    ax.set_title(title, fontsize=10, pad=8)
    ax.set_ylabel(value_col, fontsize=9)
    ax.set_xlabel("Date", fontsize=9)

    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=8, rotation=0)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(False)

    ax.xaxis.set_major_locator(mdates.DayLocator())
    try:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    except ValueError:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    # Custom legend entry for single models
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    legend_handles = [
        Line2D([0], [0], color="lightgray", linestyle=":", linewidth=1.2, label="Single model outputs"),
        Line2D([0], [0], color="darkblue", linewidth=2.0, label="Model mean"),
        Patch(facecolor="lightsteelblue", edgecolor="none", alpha=0.45, label="Mean ± 1 SD"),
    ]

    if threshold is not None:
        legend_handles.append(
            Line2D([0], [0], color="crimson", linestyle="--", linewidth=1.4, label="Critical elevation threshold")
        )

    ax.legend(
        handles=legend_handles,
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

def plot_wave_rose(df: pd.DataFrame):
    import numpy as np
    import matplotlib.pyplot as plt

    plot_df = df.copy()

    dirs = np.mod(plot_df["Dir [deg]"].to_numpy(dtype=float), 360.0)
    hs = plot_df["Hs [m]"].to_numpy(dtype=float)

    # 16 directional sectors
    dir_edges = np.arange(0, 361, 22.5)
    dir_centers = np.deg2rad((dir_edges[:-1] + dir_edges[1:]) / 2.0)
    width = np.deg2rad(22.5)

    # Simpler Hs classes
    hs_bins = [0, 1, 2, 4, np.inf]
    hs_labels = ["0–1", "1–2", "2–4", ">4"]

    counts = np.zeros((len(hs_labels), len(dir_centers)))

    dir_idx = np.digitize(dirs, dir_edges, right=False) - 1
    dir_idx[dir_idx == len(dir_centers)] = 0

    hs_idx = np.digitize(hs, hs_bins, right=False) - 1
    hs_idx = np.clip(hs_idx, 0, len(hs_labels) - 1)

    for i in range(len(hs)):
        counts[hs_idx[i], dir_idx[i]] += 1

    counts_pct = counts / max(counts.sum(), 1) * 100.0

    fig, ax = plt.subplots(
        figsize=(4.8, 4.8),
        dpi=160,
        subplot_kw={"projection": "polar"},
    )

    bottom = np.zeros(len(dir_centers))
    colors = ["#dbe9f6", "#9ec9f5", "#4f9be6", "#0b5cad"]

    for i, label in enumerate(hs_labels):
        ax.bar(
            dir_centers,
            counts_pct[i],
            width=width,
            bottom=bottom,
            color=colors[i],
            edgecolor="white",
            linewidth=0.6,
            align="center",
            label=f"Hs {label} m",
        )
        bottom += counts_pct[i]

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    ax.set_title("Wave rose", fontsize=10, pad=14)

    ax.tick_params(labelsize=8)
    ax.grid(color="0.7", linewidth=0.8)

    ax.spines["polar"].set_linewidth(1.0)

    ax.legend(
        frameon=False,
        fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=2,
    )

    fig.tight_layout()
    return fig


def plot_wave_climate_timeseries(df: pd.DataFrame):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(7.2, 4.4),
        dpi=160,
        sharex=True,
    )

    time = pd.to_datetime(df["time"])

    axes[0].plot(time, df["Hs [m]"], color="skyblue", linewidth=1.5)
    axes[0].set_ylabel("Hs [m]", fontsize=9)
    axes[0].set_title("Extracted wave time series", fontsize=10, pad=8)

    axes[1].plot(time, df["Tp [s]"], color="goldenrod", linewidth=1.5)
    axes[1].set_ylabel("Tp [s]", fontsize=9)

    for ax in axes:
        ax.tick_params(axis="y", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(False)

    axes[1].xaxis.set_major_locator(mdates.YearLocator(base=2))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[1].tick_params(axis="x", labelsize=8, rotation=0)
    axes[1].set_xlabel("Date", fontsize=9)

    fig.tight_layout()
    return fig



def plot_return_values(return_df: pd.DataFrame):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=160)

    ax.plot(
        return_df["Return period [years]"],
        return_df["Return Hs [m]"],
        marker="o",
        linewidth=1.8,
        color="darkblue",
    )

    ax.set_xscale("log")
    ax.set_xlabel("Return period [years]", fontsize=9)
    ax.set_ylabel("Return Hs [m]", fontsize=9)
    ax.set_title("Sector-based return values of Hs", fontsize=10, pad=8)

    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(False)

    fig.tight_layout()
    return fig