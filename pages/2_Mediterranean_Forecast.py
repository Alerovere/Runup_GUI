import folium
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src.copernicus_io import MED_DATASET_ID, fetch_copernicus_wave_timeseries
from src.plotting import plot_envelope, plot_wave_timeseries
from src.runup_models import RunupInputs, compute_runup


def compute_forecast_envelope(forecast_df: pd.DataFrame, slope: float, swl: float):
    detail_rows = []

    for _, row in forecast_df.iterrows():
        values = RunupInputs(
            hs=float(row["Hs [m]"]),
            tp=float(row["Tp [s]"]),
            slope=float(slope),
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
        )
        .reset_index()
    )

    return detail_df, envelope_df


st.title("Mediterranean forecast")

st.info(
    "Use this page to extract a single-point Mediterranean wave forecast from Copernicus Marine "
    "and compute weekly envelopes of runup and total water level across empirical models. "
    "Select a point on the map and, if needed, refine it with the coordinate fields."
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

    swl = st.number_input(
        "Tide + storm surge eta [m]",
        value=0.0,
        step=0.1,
        format="%.3f",
        help="Still-water-level offset added to runup to estimate total water level.",
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

if "selected_lat" not in st.session_state:
    st.session_state.selected_lat = 41.9000
if "selected_lon" not in st.session_state:
    st.session_state.selected_lon = 12.5000
if "map_center" not in st.session_state:
    st.session_state.map_center = [
        st.session_state.selected_lat,
        st.session_state.selected_lon,
    ]
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 5

st.subheader("Select forecast point")
st.write(
    "Click on the map to place the forecast point. The map preserves its zoom and center."
)

m = folium.Map(
    location=st.session_state.map_center,
    zoom_start=st.session_state.map_zoom,
    control_scale=True,
)

folium.Marker(
    [st.session_state.selected_lat, st.session_state.selected_lon],
    tooltip="Forecast point",
).add_to(m)

map_data = st_folium(
    m,
    width=900,
    height=500,
    returned_objects=["last_clicked", "center", "zoom"],
    key="forecast_map",
)

if map_data:
    if map_data.get("center"):
        st.session_state.map_center = [
            float(map_data["center"]["lat"]),
            float(map_data["center"]["lng"]),
        ]

    if map_data.get("zoom") is not None:
        st.session_state.map_zoom = int(map_data["zoom"])

    if map_data.get("last_clicked"):
        new_lat = float(map_data["last_clicked"]["lat"])
        new_lon = float(map_data["last_clicked"]["lng"])

        if (
            new_lat != st.session_state.selected_lat
            or new_lon != st.session_state.selected_lon
        ):
            st.session_state.selected_lat = new_lat
            st.session_state.selected_lon = new_lon
            st.session_state.map_center = [new_lat, new_lon]
            st.rerun()

col1, col2 = st.columns(2)
with col1:
    new_lat_input = st.number_input(
        "Latitude [deg]",
        value=float(st.session_state.selected_lat),
        format="%.5f",
        key="forecast_lat_input",
    )
with col2:
    new_lon_input = st.number_input(
        "Longitude [deg]",
        value=float(st.session_state.selected_lon),
        format="%.5f",
        key="forecast_lon_input",
    )

if (
    new_lat_input != st.session_state.selected_lat
    or new_lon_input != st.session_state.selected_lon
):
    st.session_state.selected_lat = float(new_lat_input)
    st.session_state.selected_lon = float(new_lon_input)

st.caption(
    f"Selected coordinates: lat = {st.session_state.selected_lat:.5f}, "
    f"lon = {st.session_state.selected_lon:.5f}"
)

if not fetch_button:
    st.info("Select a point and click Fetch Mediterranean forecast.")
    st.stop()

username = st.secrets.get("COPERNICUSMARINE_USERNAME") or st.secrets.get("COPERNICUS_USERNAME")
password = st.secrets.get("COPERNICUSMARINE_PASSWORD") or st.secrets.get("COPERNICUS_PASSWORD")

if not username or not password:
    st.error("Copernicus credentials are missing in Streamlit secrets.")
    st.stop()

with st.spinner("Downloading Mediterranean wave forecast..."):
    forecast_df, hs_var, period_var = fetch_copernicus_wave_timeseries(
        longitude=st.session_state.selected_lon,
        latitude=st.session_state.selected_lat,
        username=username,
        password=password,
    )
    _, envelope_df = compute_forecast_envelope(forecast_df, slope, swl)

if envelope_df.empty:
    st.warning("No forecast-based runup results were computed.")
    st.stop()

st.caption(f"Dataset ID: {MED_DATASET_ID}")
st.caption(f"Using variables: Hs = {hs_var}, period = {period_var}")

st.subheader("Forecast preview")
st.dataframe(forecast_df, use_container_width=True, hide_index=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Forecast records", len(envelope_df))
c2.metric("Mean runup", f"{envelope_df['runup_mean'].mean():.2f} m")
c3.metric("Mean TWL", f"{envelope_df['twl_mean'].mean():.2f} m")
c4.metric("Max TWL", f"{envelope_df['twl_max'].max():.2f} m")

if threshold is not None:
    c5, c6 = st.columns(2)
    c5.metric(
        "Timesteps mean TWL > threshold",
        int((envelope_df["twl_mean"] > threshold).sum()),
    )
    c6.metric(
        "Timesteps max TWL > threshold",
        int((envelope_df["twl_max"] > threshold).sum()),
    )

st.subheader("Weekly wave forcing")
st.pyplot(
    plot_wave_timeseries(envelope_df),
    clear_figure=False,
    use_container_width=True,
)

st.subheader("Weekly runup envelope")
st.pyplot(
    plot_envelope(envelope_df, threshold=threshold, mode="runup"),
    clear_figure=False,
    use_container_width=True,
)

st.subheader("Weekly total water level envelope")
st.pyplot(
    plot_envelope(envelope_df, threshold=threshold, mode="twl"),
    clear_figure=False,
    use_container_width=True,
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

st.caption(
    "Source: European Union, Copernicus Marine Service Information or Data, "
    "implemented by Mercator Ocean International."
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
    "Copernicus Marine forecast data shown here are regional model outputs and may differ from local nearshore conditions. "
    "This page is intended for scientific exploration and teaching, not for operational coastal-risk decisions."
)