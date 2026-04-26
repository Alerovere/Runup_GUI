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

with st.sidebar:
    st.header("Forecast inputs")
    slope = st.number_input("Beach slope beta [-]", min_value=0.001, max_value=0.999, value=0.05, step=0.005, format="%.3f")
    swl = st.number_input("Tide + storm surge eta [m]", value=0.0, step=0.1, format="%.3f")
    threshold_enabled = st.checkbox("Add threshold elevation", value=True)
    threshold = st.number_input("Threshold elevation [m]", value=2.0, step=0.1, format="%.3f") if threshold_enabled else None
    fetch_button = st.button("Fetch Mediterranean forecast", type="primary", use_container_width=True)

st.write("Click on the map to select the forecast point.")

if "selected_lat" not in st.session_state:
    st.session_state.selected_lat = 41.9
if "selected_lon" not in st.session_state:
    st.session_state.selected_lon = 12.5

m = folium.Map(location=[st.session_state.selected_lat, st.session_state.selected_lon], zoom_start=5)
folium.Marker(
    [st.session_state.selected_lat, st.session_state.selected_lon],
    tooltip="Selected point",
).add_to(m)

map_data = st_folium(m, width=900, height=500)

if map_data and map_data.get("last_clicked"):
    st.session_state.selected_lat = map_data["last_clicked"]["lat"]
    st.session_state.selected_lon = map_data["last_clicked"]["lng"]

st.write(
    f"Selected coordinates: lat = {st.session_state.selected_lat:.4f}, "
    f"lon = {st.session_state.selected_lon:.4f}"
)

if not fetch_button:
    st.info("Select a point on the map, then click Fetch Mediterranean forecast.")
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
    c5.metric("Timesteps mean TWL > threshold", int((envelope_df["twl_mean"] > threshold).sum()))
    c6.metric("Timesteps max TWL > threshold", int((envelope_df["twl_max"] > threshold).sum()))

st.subheader("Weekly wave forcing")
st.pyplot(plot_wave_timeseries(envelope_df))

st.subheader("Weekly runup envelope")
st.pyplot(plot_envelope(envelope_df, threshold=threshold, mode="runup"))

st.subheader("Weekly total water level envelope")
st.pyplot(plot_envelope(envelope_df, threshold=threshold, mode="twl"))

csv_data = envelope_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download weekly envelope as CSV",
    data=csv_data,
    file_name="weekly_runup_envelope.csv",
    mime="text/csv",
)