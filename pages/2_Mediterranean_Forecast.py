import numpy as np
import pandas as pd
import streamlit as st

from src.copernicus_io import MED_DATASET_ID, fetch_copernicus_wave_timeseries
from src.copernicus_sealevel import (
    MED_SEALEVEL_DATASET_ID,
    fetch_copernicus_sealevel_timeseries,
    merge_wave_and_sealevel,
)
from src.forecast_thresholds import (
    build_daily_threshold_status,
    build_threshold_timeseries,
    describe_threshold_logic,
    describe_worst_status,
    summarize_threshold_status,
)
from src.plotting import (
    fig_to_png_bytes,
    plot_daily_threshold_bar,
    plot_forecast_model_timeseries,
    plot_wave_timeseries,
)
from src.runup_models import RunupInputs, compute_runup


def compute_forecast_envelope(
    forcing_df: pd.DataFrame,
    slope: float,
    water_level_mode: str,
    constant_eta: float = 0.0,
):
    detail_rows = []

    for _, row in forcing_df.iterrows():
        if water_level_mode == "Copernicus mean-removed sea-level signal":
            eta_value = float(row["sea-level signal [m]"])
        else:
            eta_value = float(constant_eta)

        values = RunupInputs(
            hs=float(row["Hs [m]"]),
            tp=float(row["Tp [s]"]),
            slope=float(slope),
            swl=eta_value,
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
                        "Water level [m]": eta_value,
                        "Runup [m]": float(runup),
                        "Total water level [m]": float(runup + eta_value),
                    }
                )

    detail_df = pd.DataFrame(detail_rows)
    if detail_df.empty:
        return detail_df, pd.DataFrame()

    envelope_df = (
        detail_df.groupby("time")
        .agg(
            runup_min=("Runup [m]", "min"),
            runup_mean=("Runup [m]", "mean"),
            runup_max=("Runup [m]", "max"),
            twl_min=("Total water level [m]", "min"),
            twl_mean=("Total water level [m]", "mean"),
            twl_max=("Total water level [m]", "max"),
            hs_mean=("Hs [m]", "mean"),
            tp_mean=("Tp [s]", "mean"),
            wl_mean=("Water level [m]", "mean"),
        )
        .reset_index()
    )

    return detail_df, envelope_df


st.title("Mediterranean forecast")

st.info(
    "Use this page to extract a single-point Mediterranean wave forecast from Copernicus Marine "
    "and compute weekly envelopes of runup and total water level across empirical models."
)

st.markdown(
    """
**How to choose the point**

Enter the latitude and longitude of a point that is **reasonably offshore**, rather than directly on the shoreline.
This helps avoid selecting land grid cells and is more consistent with the offshore wave-model nature of the Copernicus product.

A practical rule is to choose a point:
- just offshore of the beach or coastal sector of interest
- clearly at sea, not on land
- not inside very small harbours, lagoons, or enclosed basins
"""
)

with st.sidebar:
    st.header("Forecast inputs")

    slope = st.number_input(
        "Beach slope beta [-]",
        min_value=0.001,
        max_value=0.999,
        value=0.05,
        step=0.005,
        format="%.3f",
        help="Beach-face slope entered as a decimal, for example 0.05 = 5%.",
    )

    water_level_mode = st.radio(
        "Water-level mode",
        ["Constant tide + storm surge", "Copernicus mean-removed sea-level signal"],
        help=(
            "Use a constant still-water-level offset, or use Copernicus Mediterranean "
            "modelled sea surface height above geoid after removing the mean over the downloaded period."
        ),
    )

    constant_eta = 0.0
    if water_level_mode == "Constant tide + storm surge":
        constant_eta = st.number_input(
            "Tide + storm surge eta [m]",
            value=0.0,
            step=0.1,
            format="%.3f",
            help="Still-water-level offset added to runup to estimate total water level.",
        )
    else:
        st.caption(
            "Water level will be taken from Copernicus Mediterranean sea surface height above geoid, "
            "then centered by subtracting the mean of the downloaded period."
        )

    threshold_enabled = st.checkbox(
        "Add threshold elevation",
        value=True,
        help="Enable this to compare forecast runup or total water level against a critical elevation threshold.",
    )

    threshold = None
    if threshold_enabled:
        threshold = st.number_input(
            "Threshold elevation [m]",
            value=2.0,
            step=0.1,
            format="%.3f",
            help="Critical elevation used to interpret exceedance of model envelopes.",
        )

    fetch_button = st.button(
        "Fetch Mediterranean forecast",
        type="primary",
        use_container_width=True,
    )

if "forecast_lat" not in st.session_state:
    st.session_state.forecast_lat = 44.046833
if "forecast_lon" not in st.session_state:
    st.session_state.forecast_lon = 8.389593

st.subheader("Forecast point coordinates")

col1, col2 = st.columns(2)
with col1:
    st.session_state.forecast_lat = st.number_input(
        "Latitude [deg]",
        value=float(st.session_state.forecast_lat),
        format="%.5f",
        key="forecast_lat_input",
        help="Latitude of the offshore forecast point.",
    )
with col2:
    st.session_state.forecast_lon = st.number_input(
        "Longitude [deg]",
        value=float(st.session_state.forecast_lon),
        format="%.5f",
        key="forecast_lon_input",
        help="Longitude of the offshore forecast point.",
    )

st.caption(
    f"Selected coordinates: lat = {st.session_state.forecast_lat:.5f}, "
    f"lon = {st.session_state.forecast_lon:.5f}"
)

if not (30.0 <= st.session_state.forecast_lat <= 46.5 and -6.5 <= st.session_state.forecast_lon <= 37.0):
    st.warning(
        "These coordinates fall outside a broad Mediterranean bounding box. "
        "Double-check that the selected point is correct and located within the Mediterranean forecasting domain."
    )

st.subheader("Map preview")

map_df = pd.DataFrame(
    {
        "lat": [st.session_state.forecast_lat],
        "lon": [st.session_state.forecast_lon],
    }
)

st.map(map_df, zoom=6, use_container_width=True)

st.caption(
    "The map is shown for confirmation only. Update the coordinates in the input boxes above to move the forecast point."
)

if not fetch_button:
    st.info("Enter an offshore point and click Fetch Mediterranean forecast.")
    st.stop()

username = st.secrets.get("COPERNICUSMARINE_USERNAME") or st.secrets.get("COPERNICUS_USERNAME")
password = st.secrets.get("COPERNICUSMARINE_PASSWORD") or st.secrets.get("COPERNICUS_PASSWORD")

if not username or not password:
    st.error("Copernicus credentials are missing in Streamlit secrets.")
    st.stop()

with st.spinner("Downloading Mediterranean forecast data..."):
    wave_df, hs_var, period_var = fetch_copernicus_wave_timeseries(
        longitude=st.session_state.forecast_lon,
        latitude=st.session_state.forecast_lat,
        username=username,
        password=password,
    )

    ssh_var = None
    forcing_df = wave_df.copy()

    if water_level_mode == "Copernicus mean-removed sea-level signal":
        sealevel_df, ssh_var = fetch_copernicus_sealevel_timeseries(
            longitude=st.session_state.forecast_lon,
            latitude=st.session_state.forecast_lat,
            username=username,
            password=password,
        )
        forcing_df = merge_wave_and_sealevel(wave_df, sealevel_df)

    detail_df, envelope_df = compute_forecast_envelope(
        forcing_df,
        slope=slope,
        water_level_mode=water_level_mode,
        constant_eta=constant_eta,
    )

if envelope_df.empty:
    st.warning("No forecast-based runup results were computed.")
    st.stop()

st.caption(f"Wave dataset ID: {MED_DATASET_ID}")
st.caption(f"Using wave variables: Hs = {hs_var}, period = {period_var}")

if water_level_mode == "Copernicus mean-removed sea-level signal":
    st.caption(f"Sea-level dataset ID: {MED_SEALEVEL_DATASET_ID}")
    st.caption(f"Using sea-level variable: {ssh_var}")

st.subheader("Forecast summary")

forecast_start = pd.to_datetime(forcing_df["time"].min())
forecast_end = pd.to_datetime(forcing_df["time"].max())

max_hs_idx = forcing_df["Hs [m]"].idxmax()
max_hs_row = forcing_df.loc[max_hs_idx]

max_hs = float(max_hs_row["Hs [m]"])
max_tp = float(max_hs_row["Tp [s]"])
max_hs_time = pd.to_datetime(max_hs_row["time"])

mean_runup = float(envelope_df["runup_mean"].mean())
max_runup = float(envelope_df["runup_max"].max())

show_twl = (
    water_level_mode == "Copernicus mean-removed sea-level signal"
    or abs(constant_eta) > 0
)

st.markdown(
    f"""
**Forecast period**  
{forecast_start.strftime("%A, %B")} {forecast_start.day}, {forecast_start.year} to {forecast_end.strftime("%A, %B")} {forecast_end.day}, {forecast_end.year}

**Maximum forecast wave conditions**  
Hs max = **{max_hs:.2f} m**  
Associated peak period = **{max_tp:.2f} s**  
Expected on **{max_hs_time.strftime("%A, %B")} {max_hs_time.day}, {max_hs_time.year}**
"""
)

c1, c2 = st.columns(2)
c1.metric("Mean runup", f"{mean_runup:.2f} m")
c2.metric("Maximum runup", f"{max_runup:.2f} m")

if show_twl:
    mean_twl = float(envelope_df["twl_mean"].mean())
    max_twl = float(envelope_df["twl_max"].max())

    c3, c4 = st.columns(2)
    c3.metric("Mean TWL", f"{mean_twl:.2f} m")
    c4.metric("Maximum TWL", f"{max_twl:.2f} m")

if water_level_mode == "Copernicus mean-removed sea-level signal":
    st.caption(
        "Total water level is computed using a Copernicus Mediterranean modelled sea-level signal obtained from sea surface height above geoid after subtracting the mean over the downloaded forecast period. This is not a local tide-gauge prediction."
    )
elif abs(constant_eta) > 0:
    st.caption(
        f"Total water level is computed using a constant user-defined water-level offset of {constant_eta:.2f} m."
    )
else:
    st.caption(
        "Only runup is evaluated here, because no additional water-level offset has been applied."
    )

if threshold is not None:
    compare_value_col = "Runup [m]"
    compare_label = "runup"

    if show_twl:
        compare_value_col = "Total water level [m]"
        compare_label = "total water level"

    threshold_ts_df = build_threshold_timeseries(
        detail_df=detail_df,
        value_col=compare_value_col,
        threshold=float(threshold),
    )

    daily_status_df = build_daily_threshold_status(threshold_ts_df)
    threshold_summary = summarize_threshold_status(threshold_ts_df)

    st.subheader("Daily threshold status")
    st.pyplot(
        plot_daily_threshold_bar(
            daily_status_df,
            title=f"Daily threshold status for forecast {compare_label}",
        ),
        clear_figure=False,
        use_container_width=True,
    )

    st.markdown(describe_threshold_logic(compare_label, float(threshold)))

    st.markdown(
        f"<div style='padding:0.6rem 0.8rem;border-radius:0.5rem;background:{threshold_summary['worst_color']};color:white;font-weight:600;'>{describe_worst_status(threshold_summary['worst_status'], float(threshold), compare_label)}</div>",
        unsafe_allow_html=True,
    )

    if threshold_summary["first_exceedance"] is not None:
        first_ex = threshold_summary["first_exceedance"]
        st.caption(
            "First non-green exceedance: "
            + first_ex.strftime("%A, %B ")
            + str(first_ex.day)
            + first_ex.strftime(", %Y %H:%M")
        )

st.subheader("Weekly wave forcing")
st.pyplot(
    plot_wave_timeseries(envelope_df),
    clear_figure=False,
    use_container_width=True,
)

st.caption(
    "This figure shows the forecast wave forcing extracted at the selected offshore point."
)

plot_value_col = "Runup [m]"
plot_title = "Forecast runup across empirical models"

if show_twl:
    plot_value_col = "Total water level [m]"
    plot_title = "Forecast total water level across empirical models"

st.subheader("Forecast model time series")

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_forecast = plot_forecast_model_timeseries(
        detail_df=detail_df,
        value_col=plot_value_col,
        threshold=threshold,
        title=plot_title,
    )
    forecast_png = fig_to_png_bytes(fig_forecast)
    st.pyplot(fig_forecast, clear_figure=False, use_container_width=False)

st.download_button(
    label="Download forecast graph (PNG)",
    data=forecast_png,
    file_name="forecast_model_timeseries.png",
    mime="image/png",
)

if show_twl:
    st.caption(
        "The dotted gray lines show the individual empirical model outputs through time. "
        "The dark blue line is the model mean, the blue envelope shows ±1 standard deviation, "
        "and the red dashed line marks the critical elevation threshold."
    )
else:
    st.caption(
        "The dotted gray lines show the individual empirical runup model outputs through time. "
        "The dark blue line is the model mean, the blue envelope shows ±1 standard deviation, "
        "and the red dashed line marks the critical elevation threshold."
    )

st.subheader("Envelope data")
st.dataframe(envelope_df, use_container_width=True, hide_index=True)

csv_data = envelope_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download weekly envelope as CSV",
    data=csv_data,
    file_name="weekly_runup_envelope.csv",
    mime="text/csv",
)

st.subheader("Copernicus Marine data source and licence")

st.caption(
    "This page uses the Copernicus Marine product "
    "'Mediterranean Sea Waves Analysis and Forecast' "
    "(Product ID: MEDSEA_ANALYSISFORECAST_WAV_006_017; DOI: 10.48670/mds-00373)."
)

if water_level_mode == "Copernicus mean-removed sea-level signal":
    st.caption(
        "It also uses the Copernicus Marine Mediterranean sea-level forecast dataset "
        f"({MED_SEALEVEL_DATASET_ID}) and derives a mean-removed sea-level signal from sea surface height above geoid."
    )

st.caption(
    "Source: European Union, Copernicus Marine Service Information or Data, implemented by Mercator Ocean International."
)

st.markdown(
    """
Generated using **E.U. Copernicus Marine Service Information**.

**Recommended product citation**  
*Mediterranean Sea Waves Analysis and Forecast. E.U. Copernicus Marine Service Information (CMEMS). Marine Data Store (MDS). DOI: 10.48670/mds-00373 (accessed on 26 Apr 2026).*

This application uses Copernicus Marine data to generate a derivative educational product.  
Use of Copernicus Marine information remains subject to the Copernicus Marine licence and terms of service.
"""
)

st.info(
    "Copernicus Marine forecast data shown here are regional model outputs and may differ from local nearshore conditions. This page is intended for scientific exploration and teaching, not for operational coastal-risk decisions."
)