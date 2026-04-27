import numpy as np
import pandas as pd
import streamlit as st

from src.plotting import (
    fig_to_png_bytes,
    plot_profile_with_runup,
    plot_runup_twl_comparison,
)
from src.profile_tools import read_profile
from src.runup_models import MODEL_ORDER, RunupInputs, compute_runup


def compute_risk_status(results_df: pd.DataFrame, include_swl: bool, threshold: float):
    compare_col = "Total water level [m]" if include_swl else "Runup [m]"
    values = results_df[compare_col].to_numpy(dtype=float)

    mean_val = float(np.mean(values))
    std_val = float(np.std(values, ddof=0))
    max_val = float(np.max(values))

    if threshold > max_val:
        return (
            "green",
            "GREEN",
            f"The critical threshold ({threshold:.2f} m) is above all model outputs.",
        )
    if threshold > mean_val + std_val:
        return (
            "#d8b400",
            "YELLOW",
            f"The threshold ({threshold:.2f} m) is exceeded by some individual models, but remains above the mean + 1 SD level.",
        )
    if threshold > mean_val - std_val:
        return (
            "orange",
            "ORANGE",
            f"The threshold ({threshold:.2f} m) lies within the mean ± 1 SD range of the model outputs.",
        )
    return (
        "red",
        "RED",
        f"The threshold ({threshold:.2f} m) is below the mean - 1 SD level, indicating robust exceedance across the model spread.",
    )


st.title("Manual calculator")

st.info(
    "Use this page to estimate wave runup and, optionally, total water level for a single "
    "user-defined scenario. Enter representative values for significant wave height, peak wave period, "
    "and beach slope. You can optionally include tide + storm surge, define a critical elevation threshold, "
    "and upload a beach profile to visualize the modelled elevations on a cross-shore section."
)

with st.sidebar:
    st.header("Manual inputs")

    hs = st.number_input(
        "Significant wave height Hs [m]",
        min_value=0.001,
        value=1.5,
        step=0.1,
        format="%.3f",
        help="Representative offshore or nearshore significant wave height for the scenario being analysed.",
    )

    tp = st.number_input(
        "Wave period Tp [s]",
        min_value=0.001,
        value=8.0,
        step=0.1,
        format="%.3f",
        help="Representative peak wave period associated with Hs.",
    )

    slope = st.number_input(
        "Beach slope beta [-]",
        min_value=0.001,
        max_value=0.999,
        value=0.05,
        step=0.005,
        format="%.3f",
        help="Beach-face slope entered as a decimal, for example 0.05 = 5%.",
    )

    include_swl = st.checkbox(
        "Include tide + storm surge (eta)",
        value=False,
        help="Enable this if you want to add a still-water-level offset to runup.",
    )

    swl = 0.0
    if include_swl:
        swl = st.number_input(
            "Tide + storm surge eta [m]",
            value=0.0,
            step=0.1,
            format="%.3f",
            help="Still-water-level offset added to runup to estimate total water level. This value can be positive or negative depending on the reference level used.",
        )

    include_threshold = st.checkbox(
        "Include critical elevation threshold",
        value=False,
        help="Enable this to compare modelled elevations against a user-defined critical level.",
    )

    threshold = None
    if include_threshold:
        threshold = st.number_input(
            "Critical elevation threshold [m]",
            value=2.0,
            step=0.1,
            format="%.3f",
            help="Critical elevation used for a qualitative traffic-light style risk interpretation.",
        )

    uploaded_profile = st.file_uploader(
        "Upload beach profile (.csv, .txt, .dat)",
        type=["csv", "txt", "dat"],
        help="Optional beach profile with x and y columns for plotting the modelled elevations on a cross-shore section.",
    )

    calculate = st.button("Calculate", type="primary", use_container_width=True)

if not calculate:
    st.info("Set the inputs in the sidebar and click Calculate.")
    st.stop()

values = RunupInputs(hs=hs, tp=tp, slope=slope, swl=swl)
runup_results = compute_runup(values)

rows = []
for model in MODEL_ORDER:
    runup = runup_results.get(model, np.nan)
    if np.isfinite(runup):
        row = {
            "Model": model,
            "Runup [m]": round(float(runup), 3),
        }
        if include_swl:
            row["Total water level [m]"] = round(float(runup + swl), 3)
        rows.append(row)

results_df = pd.DataFrame(rows)

if results_df.empty:
    st.warning("No model returned a valid result.")
    st.stop()

st.subheader("Results table")

if include_swl:
    st.caption(
        f"Scenario used: Hs = {hs:.3f} m, Tp = {tp:.3f} s, beta = {slope:.3f}, eta = {swl:.3f} m."
    )
else:
    st.caption(
        f"Scenario used: Hs = {hs:.3f} m, Tp = {tp:.3f} s, beta = {slope:.3f}, eta not included."
    )

if include_swl:
    display_df = results_df[["Model", "Runup [m]", "Total water level [m]"]]
else:
    display_df = results_df[["Model", "Runup [m]"]]

st.dataframe(display_df, use_container_width=True, hide_index=True)

risk_color = None
risk_label = None
risk_text = None
if include_threshold and threshold is not None:
    risk_color, risk_label, risk_text = compute_risk_status(results_df, include_swl, float(threshold))

st.subheader("Model comparison")

col1, col2, col3 = st.columns([0.8, 3.4, 0.8])
with col2:
    fig_compare = plot_runup_twl_comparison(
        results_df,
        threshold=threshold if include_threshold else None,
        risk_color=risk_color,
        risk_label=risk_label,
    )
    compare_png = fig_to_png_bytes(fig_compare)
    st.pyplot(fig_compare, clear_figure=False, use_container_width=False)

compare_png = fig_to_png_bytes(fig_compare)
st.download_button(
    "Download model comparison image (PNG)",
    data=compare_png,
    file_name="model_comparison.png",
    mime="image/png",
)

if include_swl:
    st.caption(
        "This figure compares total water level results across empirical models. "
        "The darker bar shows wave runup, while the light-blue extension represents the added tide + storm surge contribution."
    )
else:
    st.caption(
        "This figure compares wave runup results across empirical models for the selected conditions."
    )

if include_threshold and threshold is not None:
    st.markdown(
        f"""
**Threshold interpretation.** The dashed red line marks the critical elevation threshold ({threshold:.2f} m).  
Green = threshold above all model outputs.  
Yellow = threshold exceeded by some individual models only.  
Orange = threshold lies within the mean ± 1 SD model range.  
Red = threshold below mean - 1 SD, indicating robust exceedance.
"""
    )
    st.markdown(
        f"<div style='padding:0.6rem 0.8rem;border-radius:0.5rem;background:{risk_color};color:white;font-weight:600;'>{risk_text}</div>",
        unsafe_allow_html=True,
    )

profile_df = read_profile(uploaded_profile)
if profile_df is not None:
    if include_swl:
        st.subheader("Beach profile")
    else:
        st.subheader("Beach profile")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        fig_profile = plot_profile_with_runup(
            profile_df,
            results_df,
            threshold=threshold if include_threshold else None,
        )
        profile_png = fig_to_png_bytes(fig_profile)
        st.pyplot(fig_profile, clear_figure=False, use_container_width=False)

    profile_png = fig_to_png_bytes(fig_profile)
    st.download_button(
        "Download beach profile image (PNG)",
        data=profile_png,
        file_name="beach_profile.png",
        mime="image/png",
    )

    if include_swl:
        st.caption(
            "The beach-profile plot shows modelled total water levels intersecting the shoreline profile. "
            "Light gray dotted lines represent individual model outputs, the dark blue line is the model mean, "
            "and the blue band shows ±1 standard deviation."
        )
    else:
        st.caption(
            "The beach-profile plot shows modelled runup elevations intersecting the shoreline profile. "
            "Light gray dotted lines represent individual model outputs, the dark blue line is the model mean, "
            "and the blue band shows ±1 standard deviation."
        )