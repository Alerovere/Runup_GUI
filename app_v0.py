import math
from dataclasses import dataclass
from io import StringIO
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

try:
    from py_wave_runup import models
except ImportError:
    models = None


@dataclass
class RunupInputs:
    hs: float
    tp: float
    slope: float
    swl: float


MODEL_ORDER = [
    "Stockdon et al. (2006)",
    "Vousdoukas et al. (2012)",
    "Holman (1986)",
    "Nielsen (2009)",
    "Ruggiero et al. (2001)",
    "Atkinson et al. (2017)",
    "Senechal et al. (2011)",
    "Passarella et al. (2018)",
]


def validate_inputs(values: RunupInputs) -> None:
    if values.hs <= 0:
        raise ValueError("Significant wave height must be greater than 0 m.")
    if values.tp <= 0:
        raise ValueError("Wave period must be greater than 0 s.")
    if values.slope <= 0:
        raise ValueError("Beach slope must be greater than 0.")
    if values.slope >= 1:
        raise ValueError("Beach slope must be entered as a decimal, for example 0.05 for a 5% slope.")


def _scalar_result(value: Any) -> float:
    arr = np.asarray(value, dtype=float)
    if arr.size == 0:
        raise ValueError("The selected model returned no value.")
    return float(arr.reshape(-1)[0])


# Conservative fallback: only Stockdon 2% runup is implemented here.
# If py_wave_runup is available, the app will use the full model suite.
def fallback_runup(values: RunupInputs) -> Dict[str, float]:
    g = 9.81
    l0 = g * values.tp ** 2 / (2 * math.pi)
    stockdon_r2 = 1.1 * (
        0.35 * values.slope * math.sqrt(values.hs * l0)
        + 0.5 * math.sqrt(values.hs * l0 * (0.563 * values.slope ** 2 + 0.004))
    )
    return {
        "Stockdon et al. (2006)": stockdon_r2,
    }



def compute_runup(values: RunupInputs) -> Dict[str, float]:
    validate_inputs(values)

    if models is None:
        return fallback_runup(values)

    hs = [values.hs]
    tp = [values.tp]
    beta = [values.slope]

    results: Dict[str, float] = {}

    model_map: Dict[str, Callable[[], float]] = {
        "Stockdon et al. (2006)": lambda: _scalar_result(models.Stockdon2006(Hs=hs, Tp=tp, beta=beta).R2),
        "Vousdoukas et al. (2012)": lambda: _scalar_result(models.Vousdoukas2012(Hs=hs, Tp=tp, beta=beta).R2),
        "Holman (1986)": lambda: _scalar_result(models.Holman1986(Hs=hs, Tp=tp, beta=beta).R2),
        "Nielsen (2009)": lambda: _scalar_result(models.Nielsen2009(Hs=hs, Tp=tp, beta=beta).R2),
        "Ruggiero et al. (2001)": lambda: _scalar_result(models.Ruggiero2001(Hs=hs, Tp=tp, beta=beta).R2),
        "Atkinson et al. (2017)": lambda: _scalar_result(models.Atkinson2017(Hs=hs, Tp=tp, beta=beta).R2),
        "Senechal et al. (2011)": lambda: _scalar_result(models.Senechal2011(Hs=hs, Tp=tp, beta=beta).R2),
        "Passarella et al. (2018)": lambda: _scalar_result(models.Passarella2018(Hs=hs, Tp=tp, beta=beta).swash),
    }

    for name in MODEL_ORDER:
        try:
            results[name] = model_map[name]()
        except Exception:
            results[name] = np.nan

    return results



def build_results_table(values: RunupInputs, runup_results: Dict[str, float]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for model_name in MODEL_ORDER:
        runup = runup_results.get(model_name, np.nan)
        if np.isfinite(runup):
            twl = runup + values.swl
            rows.append(
                {
                    "Model": model_name,
                    "Runup [m]": round(float(runup), 3),
                    "Still water level eta [m]": round(float(values.swl), 3),
                    "Total water level [m]": round(float(twl), 3),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["Model", "Runup [m]", "Still water level eta [m]", "Total water level [m]"])
    return pd.DataFrame(rows)



def read_profile(uploaded_file) -> Optional[pd.DataFrame]:
    if uploaded_file is None:
        return None

    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        raw = uploaded_file.getvalue().decode("utf-8")
        df = pd.read_csv(StringIO(raw), delim_whitespace=True, header=None)
        if df.shape[1] >= 2:
            df = df.iloc[:, :2]
            df.columns = ["x", "y"]

    lowered = {c.lower().strip(): c for c in df.columns}
    if "x" in lowered and "y" in lowered:
        xcol = lowered["x"]
        ycol = lowered["y"]
        out = df[[xcol, ycol]].copy()
        out.columns = ["x", "y"]
    elif df.shape[1] >= 2:
        out = df.iloc[:, :2].copy()
        out.columns = ["x", "y"]
    else:
        raise ValueError("Profile file must contain at least two columns representing x and y.")

    out["x"] = pd.to_numeric(out["x"], errors="coerce")
    out["y"] = pd.to_numeric(out["y"], errors="coerce")
    out = out.dropna().sort_values("x").reset_index(drop=True)

    if len(out) < 2:
        raise ValueError("Profile file must contain at least two valid x, y points.")

    return out



def plot_profile_with_runup(profile_df: pd.DataFrame, results_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(profile_df["x"], profile_df["y"], label="Beach profile")

    y_min = float(profile_df["y"].min())
    y_max = float(profile_df["y"].max())
    x_min = float(profile_df["x"].min())
    x_max = float(profile_df["x"].max())

    for _, row in results_df.iterrows():
        twl = float(row["Total water level [m]"])
        ax.hlines(twl, x_min, x_max, linestyles="--", label=row["Model"])

    ax.set_xlabel("Cross-shore distance x [m]")
    ax.set_ylabel("Elevation y [m]")
    ax.set_title("Beach profile with modelled total water levels")
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(min(y_min, results_df["Total water level [m]"].min()) - 0.5, max(y_max, results_df["Total water level [m]"].max()) + 0.5)
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.3)
    return fig



def main() -> None:
    st.set_page_config(page_title="Wave Runup Calculator", layout="wide")

    st.title("Wave Runup and Total Water Level Calculator")
    st.write(
        "Estimate wave runup and total water level from simplified inputs: significant wave height, wave period, beach slope, and still water level (tide + storm surge)."
    )

    with st.sidebar:
        st.header("Inputs")
        hs = st.number_input("Significant wave height Hs [m]", min_value=0.001, value=1.5, step=0.1, format="%.3f")
        tp = st.number_input("Wave period Tp [s]", min_value=0.001, value=8.0, step=0.1, format="%.3f")
        slope = st.number_input("Beach slope beta [-]", min_value=0.001, max_value=0.999, value=0.05, step=0.005, format="%.3f")
        swl = st.number_input(
            "Still water level eta [m]",
            value=0.0,
            step=0.1,
            format="%.3f",
            help="Use this for tide + storm surge relative to your chosen vertical datum. This value may be negative.",
        )
        st.caption("Enter beach slope as a decimal. Example: 0.05 = 5%.")

        st.header("Optional beach profile")
        uploaded_profile = st.file_uploader(
            "Upload beach profile (.csv or whitespace-delimited text)",
            type=["csv", "txt", "dat"],
            help="Expected format: two columns for x and y. Preferred headers: x,y",
        )

        calculate = st.button("Calculate", type="primary", use_container_width=True)

    values = RunupInputs(hs=hs, tp=tp, slope=slope, swl=swl)

    if calculate:
        try:
            runup_results = compute_runup(values)
            results_df = build_results_table(values, runup_results)
            profile_df = read_profile(uploaded_profile)
        except Exception as exc:
            st.error(str(exc))
            st.stop()

        if results_df.empty:
            st.warning("No model returned a valid result for the selected inputs.")
            st.stop()

        runup_mean = float(results_df["Runup [m]"].mean())
        twl_mean = float(results_df["Total water level [m]"].mean())
        runup_min = float(results_df["Runup [m]"].min())
        runup_max = float(results_df["Runup [m]"].max())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Models returned", len(results_df))
        c2.metric("Mean runup", f"{runup_mean:.2f} m")
        c3.metric("Mean total water level", f"{twl_mean:.2f} m")
        c4.metric("Runup range", f"{runup_min:.2f} to {runup_max:.2f} m")

        st.subheader("Results table")
        st.dataframe(results_df, use_container_width=True, hide_index=True)

        st.subheader("Comparison of wave runup across models")
        fig1, ax1 = plt.subplots(figsize=(8, 4.5))
        ax1.barh(results_df["Model"], results_df["Runup [m]"])
        ax1.set_xlabel("Runup [m]")
        ax1.set_ylabel("Model")
        ax1.set_title("Wave runup across models")
        ax1.grid(True, axis="x", alpha=0.3)
        st.pyplot(fig1)

        st.subheader("Comparison of total water level across models")
        fig2, ax2 = plt.subplots(figsize=(8, 4.5))
        ax2.barh(results_df["Model"], results_df["Total water level [m]"])
        ax2.set_xlabel("Total water level [m]")
        ax2.set_ylabel("Model")
        ax2.set_title("Total water level across models")
        ax2.grid(True, axis="x", alpha=0.3)
        st.pyplot(fig2)

        if profile_df is not None:
            st.subheader("Beach profile with modelled total water levels")
            st.caption("Dashed horizontal lines show modelled total water level values projected onto the uploaded profile.")
            fig = plot_profile_with_runup(profile_df, results_df)
            st.pyplot(fig)

            st.subheader("Uploaded profile preview")
            st.dataframe(profile_df, use_container_width=True, hide_index=True)

        csv_data = results_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download results as CSV",
            data=csv_data,
            file_name="wave_runup_results.csv",
            mime="text/csv",
        )

        with st.expander("Scientific notes"):
            st.markdown(
                """
                - **Runup** is the wave-driven shoreline excursion predicted by each empirical model.
                - **Still water level eta** is an external water-level offset such as tide plus storm surge.
                - **Total water level** is computed here as **runup + still water level**.
                - If a beach profile is uploaded, the app plots the profile and overlays the modelled total water levels.
                - Results depend on the assumptions and calibration range of each empirical formulation.
                """
            )

    else:
        st.info("Set the input values in the sidebar and click Calculate.")


if __name__ == "__main__":
    main()
