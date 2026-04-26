import numpy as np
import pandas as pd
import streamlit as st

from src.plotting import plot_profile_with_runup, plot_runup_twl_comparison
from src.profile_tools import read_profile
from src.runup_models import MODEL_ORDER, RunupInputs, compute_runup


st.title("Manual calculator")

st.info(
    "Use this page to estimate wave runup and, optionally, total water level for a single "
    "user-defined scenario. Enter representative values for significant wave height, peak wave period, "
    "and beach slope. You can optionally include tide + storm surge and upload a beach profile "
    "to visualize the modelled elevations on a cross-shore section."
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

st.subheader("Model comparison")
st.pyplot(plot_runup_twl_comparison(results_df))

profile_df = read_profile(uploaded_profile)
if profile_df is not None:
    if include_swl:
        st.subheader("Beach profile with modelled total water levels")
    else:
        st.subheader("Beach profile with modelled runup elevations")

    st.pyplot(plot_profile_with_runup(profile_df, results_df))
    st.dataframe(profile_df, use_container_width=True, hide_index=True)