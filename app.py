import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any, Callable, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

try:
    import copernicusmarine
except ImportError:
    copernicusmarine = None

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

MED_PRODUCT_ID = "MEDSEA_ANALYSISFORECAST_WAV_006_017"
PREFERRED_PERIOD_VARS = [
    "VTPK",
    "VTM10",
    "VTM02",
    "sea_surface_wave_period_at_variance_spectral_density_maximum",
    "sea_surface_wave_mean_period_from_variance_spectral_density_inverse_frequency_moment",
    "sea_surface_wave_mean_period_from_variance_spectral_density_second_frequency_moment",
]
PREFERRED_HS_VARS = [
    "VHM0",
    "sea_surface_wave_significant_height",
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
        df = pd.read_csv(StringIO(raw), sep=r"\s+", header=None)
        if df.shape[1] >= 2:
            df = df.iloc[:, :2]
            df.columns = ["x", "y"]

    lowered = {c.lower().strip(): c for c in df.columns}
    if "x" in lowered and "y" in lowered:
        out = df[[lowered["x"], lowered["y"]]].copy()
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



def _find_first_present_name(candidates: List[str], names: List[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_copernicus_wave_timeseries(
    longitude: float,
    latitude: float,
    period_choice: str,
    username: str,
    password: str,
) -> pd.DataFrame:
    if copernicusmarine is None:
        raise ImportError("copernicusmarine is not installed.")

    start_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=7)

    ds = copernicusmarine.open_dataset(
        dataset_id="MEDSEA_ANALYSISFORECAST_WAV_006_017",
        minimum_longitude=longitude,
        maximum_longitude=longitude,
        minimum_latitude=latitude,
        maximum_latitude=latitude,
        start_datetime=start_dt.isoformat(),
        end_datetime=end_dt.isoformat(),
        username=username,
        password=password,
    )

    data_vars = list(ds.data_vars)
    hs_var = _find_first_present_name(PREFERRED_HS_VARS, data_vars)
    if hs_var is None:
        raise ValueError(f"Could not find significant wave height variable in dataset. Available variables: {data_vars}")

    if period_choice == "Peak period":
        period_var = _find_first_present_name([PREFERRED_PERIOD_VARS[0], PREFERRED_PERIOD_VARS[3]], data_vars)
    elif period_choice == "Mean period (Tm-1,0)":
        period_var = _find_first_present_name([PREFERRED_PERIOD_VARS[1], PREFERRED_PERIOD_VARS[4]], data_vars)
    else:
        period_var = _find_first_present_name([PREFERRED_PERIOD_VARS[2], PREFERRED_PERIOD_VARS[5]], data_vars)

    if period_var is None:
        raise ValueError(f"Could not find selected wave period variable in dataset. Available variables: {data_vars}")

    hs_da = ds[hs_var].squeeze()
    tp_da = ds[period_var].squeeze()

    for dim in list(hs_da.dims):
        if dim != "time" and hs_da.sizes.get(dim, 1) == 1:
            hs_da = hs_da.isel({dim: 0})
    for dim in list(tp_da.dims):
        if dim != "time" and tp_da.sizes.get(dim, 1) == 1:
            tp_da = tp_da.isel({dim: 0})

    times = pd.to_datetime(hs_da["time"].values)
    df = pd.DataFrame(
        {
            "time": times,
            "Hs [m]": np.asarray(hs_da.values, dtype=float).reshape(-1),
            "Tp [s]": np.asarray(tp_da.values, dtype=float).reshape(-1),
        }
    )
    df = df.dropna().reset_index(drop=True)
    if df.empty:
        raise ValueError("No forecast records were returned for this point.")
    return df



def compute_forecast_envelope(forecast_df: pd.DataFrame, slope: float, swl: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows: List[Dict[str, Any]] = []

    for _, row in forecast_df.iterrows():
        values = RunupInputs(
            hs=float(row["Hs [m]"]),
            tp=float(row["Tp [s]"])
            ,slope=float(slope),
            swl=float(swl),
        )
        runup_results = compute_runup(values)
        for model_name, runup in runup_results.items():
            if np.isfinite(runup):
                detail_rows.append(
                    {
                        "time": row["time"],
                        "Model": model_name,
                        "Hs [m]": values.hs,
                        "Tp [s]": values.tp,
                        "Runup [m]": float(runup),
                        "Total water level [m]": float(runup + swl),
                    }
                )

    detail_df = pd.DataFrame(detail_rows)
    if detail_df.empty:
        return detail_df, pd.DataFrame()

    envelope_df = detail_df.groupby("time").agg(
        runup_min=("Runup [m]", "min"),
        runup_mean=("Runup [m]", "mean"),
        runup_max=("Runup [m]", "max"),
        twl_min=("Total water level [m]", "min"),
        twl_mean=("Total water level [m]", "mean"),
        twl_max=("Total water level [m]", "max"),
        hs_mean=("Hs [m]", "mean"),
        tp_mean=("Tp [s]", "mean"),
    ).reset_index()

    return detail_df, envelope_df



def plot_envelope(envelope_df: pd.DataFrame, threshold: Optional[float] = None, mode: str = "twl"):
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

    ax.fill_between(envelope_df["time"], low, high, alpha=0.25, label="Model range (min-max)")
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
    ax.plot(envelope_df["time"], envelope_df["hs_mean"], label="Hs")
    ax.plot(envelope_df["time"], envelope_df["tp_mean"], label="Tp")
    ax.set_title("Forecast wave conditions at selected point")
    ax.set_xlabel("Time")
    ax.set_ylabel("Value")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    return fig



def render_manual_tab():
    st.header("Manual runup calculator")
    with st.sidebar:
        st.subheader("Manual inputs")
        hs = st.number_input("Significant wave height Hs [m]", min_value=0.001, value=1.5, step=0.1, format="%.3f", key="manual_hs")
        tp = st.number_input("Wave period Tp [s]", min_value=0.001, value=8.0, step=0.1, format="%.3f", key="manual_tp")
        slope = st.number_input("Beach slope beta [-]", min_value=0.001, max_value=0.999, value=0.05, step=0.005, format="%.3f", key="manual_slope")
        swl = st.number_input("Tide + storm surge (eta) [m]", value=0.0, step=0.1, format="%.3f", key="manual_swl")
        uploaded_profile = st.file_uploader("Upload beach profile (.csv, .txt, .dat)", type=["csv", "txt", "dat"], key="manual_profile")
        calculate = st.button("Calculate manual scenario", type="primary", use_container_width=True)

    if not calculate:
        st.info("Set the manual inputs in the sidebar and click Calculate manual scenario.")
        return

    values = RunupInputs(hs=hs, tp=tp, slope=slope, swl=swl)
    runup_results = compute_runup(values)
    results_df = build_results_table(values, runup_results)
    profile_df = read_profile(uploaded_profile)

    if results_df.empty:
        st.warning("No model returned a valid result for the selected inputs.")
        return

    st.subheader("Results table")
    st.dataframe(results_df, use_container_width=True, hide_index=True)

    st.subheader("Comparison of wave runup across models")
    fig1, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.barh(results_df["Model"], results_df["Runup [m]"])
    ax1.set_xlabel("Runup [m]")
    ax1.set_ylabel("Model")
    ax1.grid(True, axis="x", alpha=0.3)
    st.pyplot(fig1)

    st.subheader("Comparison of total water level across models")
    fig2, ax2 = plt.subplots(figsize=(8, 4.5))
    ax2.barh(results_df["Model"], results_df["Total water level [m]"])
    ax2.set_xlabel("Total water level [m]")
    ax2.set_ylabel("Model")
    ax2.grid(True, axis="x", alpha=0.3)
    st.pyplot(fig2)

    if profile_df is not None:
        st.subheader("Beach profile with modelled total water levels")
        st.pyplot(plot_profile_with_runup(profile_df, results_df))
        st.dataframe(profile_df, use_container_width=True, hide_index=True)



def render_forecast_tab():
    st.header("Mediterranean forecast from coordinates")
    st.write("Fetch a single-point Mediterranean wave forecast from Copernicus Marine, then compute runup and total water level envelopes across empirical models.")

    with st.sidebar:
        st.subheader("Forecast inputs")
        longitude = st.number_input("Longitude [deg]", value=12.50, format="%.4f", key="forecast_lon")
        latitude = st.number_input("Latitude [deg]", value=41.90, format="%.4f", key="forecast_lat")
        slope = st.number_input("Beach slope beta [-]", min_value=0.001, max_value=0.999, value=0.05, step=0.005, format="%.3f", key="forecast_slope")
        swl = st.number_input("Tide + storm surge (eta) [m]", value=0.0, step=0.1, format="%.3f", key="forecast_swl")
        threshold_enabled = st.checkbox("Add threshold elevation", value=True, key="forecast_threshold_enabled")
        threshold = st.number_input("Threshold elevation [m]", value=2.0, step=0.1, format="%.3f", key="forecast_threshold") if threshold_enabled else None
        period_choice = st.selectbox("Wave period variable", ["Peak period", "Mean period (Tm-1,0)", "Mean period (Tm0,2)"], index=0, key="forecast_period_choice")
        fetch_button = st.button("Fetch Mediterranean forecast", type="primary", use_container_width=True)

    if not fetch_button:
        st.info("Set coordinates and coastal parameters in the sidebar, then click Fetch Mediterranean forecast.")
        return

    username = st.secrets.get("COPERNICUSMARINE_USERNAME") or st.secrets.get("COPERNICUS_USERNAME")
    password = st.secrets.get("COPERNICUSMARINE_PASSWORD") or st.secrets.get("COPERNICUS_PASSWORD")
    if not username or not password:
        st.error("Copernicus credentials are missing. Add them to Streamlit secrets before using the forecast tab.")
        return

    try:
        with st.spinner("Downloading Mediterranean wave forecast for the selected point..."):
            forecast_df = fetch_copernicus_wave_timeseries(longitude, latitude, period_choice, username, password)
            detail_df, envelope_df = compute_forecast_envelope(forecast_df, slope, swl)
    except Exception as exc:
        st.error(f"Forecast retrieval or processing failed: {exc}")
        return

    if envelope_df.empty:
        st.warning("No forecast-based runup results were computed.")
        return

    st.subheader("Forecast preview")
    st.dataframe(forecast_df, use_container_width=True, hide_index=True)

    exceed_mean = int((envelope_df["twl_mean"] > threshold).sum()) if threshold is not None else 0
    exceed_max = int((envelope_df["twl_max"] > threshold).sum()) if threshold is not None else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Forecast records", len(envelope_df))
    c2.metric("Mean runup (weekly mean)", f"{envelope_df['runup_mean'].mean():.2f} m")
    c3.metric("Mean TWL (weekly mean)", f"{envelope_df['twl_mean'].mean():.2f} m")
    c4.metric("Max TWL", f"{envelope_df['twl_max'].max():.2f} m")

    if threshold is not None:
        c5, c6 = st.columns(2)
        c5.metric("Timesteps mean TWL > threshold", exceed_mean)
        c6.metric("Timesteps max TWL > threshold", exceed_max)

    st.subheader("Weekly wave forcing")
    st.pyplot(plot_wave_timeseries(envelope_df))

    st.subheader("Weekly runup envelope")
    st.pyplot(plot_envelope(envelope_df, threshold=threshold, mode="runup"))

    st.subheader("Weekly total water level envelope")
    st.pyplot(plot_envelope(envelope_df, threshold=threshold, mode="twl"))

    st.subheader("Envelope data")
    st.dataframe(envelope_df, use_container_width=True, hide_index=True)

    csv_data = envelope_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download weekly envelope as CSV",
        data=csv_data,
        file_name="weekly_runup_envelope.csv",
        mime="text/csv",
    )



def main() -> None:
    st.set_page_config(page_title="Wave Runup and TWL Calculator", layout="wide")
    st.title("Wave Runup and Total Water Level Calculator")
    st.caption("Manual calculator and Mediterranean forecast mode using Copernicus Marine point extraction.")

    tab1, tab2 = st.tabs(["Manual input", "Mediterranean forecast"])
    with tab1:
        render_manual_tab()
    with tab2:
        render_forecast_tab()

    with st.expander("Scientific notes"):
        st.markdown(
            """
            - Manual mode computes wave runup and total water level from user-supplied Hs, Tp, beach slope, and still water level.
            - Forecast mode retrieves Mediterranean wave conditions at a single point and computes runup envelopes across empirical models.
            - The threshold is compared against total water level, not runup alone.
            - Tide and storm surge are treated here as a user-specified constant offset.
            - Mediterranean forecast data are offshore model values and may differ from local nearshore wave conditions.
            """
        )


if __name__ == "__main__":
    main()
