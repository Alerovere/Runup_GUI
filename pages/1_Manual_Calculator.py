import numpy as np
import pandas as pd
import streamlit as st

from src.plotting import plot_barh, plot_profile_with_runup
from src.profile_tools import read_profile
from src.runup_models import MODEL_ORDER, RunupInputs, compute_runup


st.title("Manual calculator")

with st.sidebar:
    st.header("Manual inputs")
    hs = st.number_input("Significant wave height Hs [m]", min_value=0.001, value=1.5, step=0.1, format="%.3f")
    tp = st.number_input("Wave period Tp [s]", min_value=0.001, value=8.0, step=0.1, format="%.3f")
    slope = st.number_input("Beach slope beta [-]", min_value=0.001, max_value=0.999, value=0.05, step=0.005, format="%.3f")
    swl = st.number_input("Tide + storm surge eta [m]", value=0.0, step=0.1, format="%.3f")
    uploaded_profile = st.file_uploader("Upload beach profile (.csv, .txt, .dat)", type=["csv", "txt", "dat"])
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
        rows.append(
            {
                "Model": model,
                "Runup [m]": round(float(runup), 3),
                "Tide + storm surge eta [m]": round(float(swl), 3),
                "Total water level [m]": round(float(runup + swl), 3),
            }
        )

results_df = pd.DataFrame(rows)

if results_df.empty:
    st.warning("No model returned a valid result.")
    st.stop()

st.subheader("Results table")
st.dataframe(results_df, use_container_width=True, hide_index=True)

st.pyplot(
    plot_barh(
        results_df,
        "Model",
        "Runup [m]",
        "Comparison of wave runup across models",
        "Runup [m]",
    )
)

st.pyplot(
    plot_barh(
        results_df,
        "Model",
        "Total water level [m]",
        "Comparison of total water level across models",
        "Total water level [m]",
    )
)

profile_df = read_profile(uploaded_profile)
if profile_df is not None:
    st.subheader("Beach profile with modelled total water levels")
    st.pyplot(plot_profile_with_runup(profile_df, results_df))
    st.dataframe(profile_df, use_container_width=True, hide_index=True)