import pandas as pd
import streamlit as st

from src.multi_source_forecast import (
    GEFS_WAVE_FORECAST_HOURS,
    GEFS_WAVE_MEMBERS,
    MED_WAVE_FORECAST_DATASET_ID,
    fetch_copernicus_med_wave_forecast,
    fetch_noaa_gefs_wave_ensemble,
    fetch_openmeteo_wave_forecast,
    merge_multi_source,
)
from src.plotting import (
    fig_to_png_bytes,
    plot_forecast_model_timeseries,
    plot_multi_source_hs_comparison,
)

st.title("Multi-Source Forecast")

st.info(
    "Use this page to compare independent wave forecasts at a single offshore point. "
    "Significant wave height, peak period, and mean direction are pulled from up to three sources "
    "and merged into one table, so you can cross-check how much the sources agree."
)

st.markdown(
    """
Sources compared on this page:

- **Copernicus Marine** - Mediterranean Sea Waves Analysis and Forecast (same product used on the Mediterranean forecast page)
- **NOAA GEFS-Wave ensemble** - all 31 members (1 control + 30 perturbed) of NOAA's global wave ensemble, pulled directly
  from NOAA's GRIB feed. This source is noticeably slower than the other two (roughly 1-3 minutes) because there is no
  bulk download option: each of the 31 members requires its own series of requests.
- **Open-Meteo Marine** - free aggregator of several global wave models (no account needed)

Enter a point that is **reasonably offshore**, rather than directly on the shoreline, to avoid land grid cells.
"""
)

with st.sidebar:
    st.header("Multi-source forecast inputs")

    use_copernicus = st.checkbox("Copernicus Marine", value=True)
    use_noaa = st.checkbox("NOAA GEFS-Wave ensemble (31 members)", value=True)
    use_openmeteo = st.checkbox("Open-Meteo Marine", value=True)

    forecast_days = st.slider(
        "Forecast horizon [days]",
        min_value=1,
        max_value=7,
        value=4,
        help=(
            "Number of days ahead to request from each source. Open-Meteo and Copernicus support up to 7 days; "
            "the NOAA GEFS-Wave ensemble is capped at 4 days (every 6 hours) to keep the number of requests manageable."
        ),
    )

    fetch_button = st.button(
        "Fetch multi-source forecast",
        type="primary",
        use_container_width=True,
    )

if "multi_source_lat" not in st.session_state:
    st.session_state.multi_source_lat = 44.046833
if "multi_source_lon" not in st.session_state:
    st.session_state.multi_source_lon = 8.389593

st.subheader("Forecast point coordinates")
st.caption("These coordinates define the offshore point from which all forecasts are extracted.")

col1, col2 = st.columns(2)
with col1:
    st.session_state.multi_source_lat = st.number_input(
        "Latitude [deg]",
        value=float(st.session_state.multi_source_lat),
        format="%.5f",
        key="multi_source_lat_input",
        help="Latitude of the offshore forecast point.",
    )
with col2:
    st.session_state.multi_source_lon = st.number_input(
        "Longitude [deg]",
        value=float(st.session_state.multi_source_lon),
        format="%.5f",
        key="multi_source_lon_input",
        help="Longitude of the offshore forecast point.",
    )

st.caption(
    f"Selected coordinates: lat = {st.session_state.multi_source_lat:.5f}, "
    f"lon = {st.session_state.multi_source_lon:.5f}"
)

st.subheader("Map preview")
st.caption("The map is shown for confirmation only. Update the coordinate fields above to move the forecast point.")

map_df = pd.DataFrame(
    {
        "lat": [st.session_state.multi_source_lat],
        "lon": [st.session_state.multi_source_lon],
    }
)
st.map(map_df, zoom=6, use_container_width=True)

if not fetch_button:
    st.info("Enter an offshore point, choose which sources to include, and click Fetch multi-source forecast.")
    st.stop()

if not (use_copernicus or use_noaa or use_openmeteo):
    st.error("Select at least one forecast source.")
    st.stop()

lat = st.session_state.multi_source_lat
lon = st.session_state.multi_source_lon

source_frames = {}
source_notes = []
noaa_detail_df = None
noaa_metadata = None

if use_copernicus:
    username = st.secrets.get("COPERNICUSMARINE_USERNAME") or st.secrets.get("COPERNICUS_USERNAME")
    password = st.secrets.get("COPERNICUSMARINE_PASSWORD") or st.secrets.get("COPERNICUS_PASSWORD")

    if not username or not password:
        st.warning("Copernicus credentials are missing in Streamlit secrets. Skipping this source.")
    else:
        with st.spinner("Downloading Copernicus Marine forecast..."):
            try:
                source_frames["Copernicus"] = fetch_copernicus_med_wave_forecast(
                    longitude=lon,
                    latitude=lat,
                    username=username,
                    password=password,
                    forecast_days=forecast_days,
                )
                source_notes.append(f"Copernicus Marine dataset ID: `{MED_WAVE_FORECAST_DATASET_ID}`")
            except Exception as e:
                st.warning(f"Copernicus Marine fetch failed: {e}")

if use_noaa:
    with st.spinner(
        f"Downloading NOAA GEFS-Wave ensemble ({len(GEFS_WAVE_MEMBERS)} members x up to "
        f"{len(GEFS_WAVE_FORECAST_HOURS)} forecast hours)... this can take 1-3 minutes."
    ):
        try:
            noaa_detail_df, noaa_summary_df, noaa_metadata = fetch_noaa_gefs_wave_ensemble(
                longitude=lon,
                latitude=lat,
                forecast_days=forecast_days,
            )
            source_frames["NOAA GEFS-Wave"] = noaa_summary_df[["time", "Hs [m]", "Tp [s]", "Dir [deg]"]]
            source_notes.append(
                f"NOAA GEFS-Wave ensemble, cycle {noaa_metadata['cycle_date']} {noaa_metadata['cycle_hour']:02d}Z "
                f"({noaa_metadata['succeeded']}/{noaa_metadata['requested']} member-hour requests succeeded)"
            )
        except Exception as e:
            st.warning(f"NOAA GEFS-Wave ensemble fetch failed: {e}")

if use_openmeteo:
    with st.spinner("Downloading Open-Meteo Marine forecast..."):
        try:
            source_frames["Open-Meteo"] = fetch_openmeteo_wave_forecast(
                longitude=lon,
                latitude=lat,
                forecast_days=forecast_days,
            )
            source_notes.append("Open-Meteo Marine API: `https://marine-api.open-meteo.com/v1/marine`")
        except Exception as e:
            st.warning(f"Open-Meteo Marine fetch failed: {e}")

if not source_frames:
    st.error("None of the selected sources returned data for this point. Try a different location or fewer sources.")
    st.stop()

combined_df = merge_multi_source(source_frames)

st.subheader("Sources used")
for note in source_notes:
    st.caption(note)

st.subheader("Hs comparison")
st.caption(
    "Significant wave height through the forecast period, one line per source. "
    "For NOAA, this line is the GEFS-Wave ensemble mean."
)

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_hs = plot_multi_source_hs_comparison(combined_df, list(source_frames.keys()))
    hs_png = fig_to_png_bytes(fig_hs)
    st.pyplot(fig_hs, clear_figure=False, use_container_width=False)

st.download_button(
    "Download Hs comparison plot (PNG)",
    data=hs_png,
    file_name="multi_source_hs_comparison.png",
    mime="image/png",
)

if noaa_detail_df is not None:
    st.subheader("NOAA GEFS-Wave ensemble spread")
    st.caption(
        "Each light gray dotted line is one of the 31 ensemble members. The dark blue line is the ensemble mean, "
        "and the shaded band is the mean +/- 1 standard deviation across members."
    )

    col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
    with col2:
        fig_ens = plot_forecast_model_timeseries(
            detail_df=noaa_detail_df,
            value_col="Hs [m]",
            title="GEFS-Wave ensemble Hs spread",
        )
        ens_png = fig_to_png_bytes(fig_ens)
        st.pyplot(fig_ens, clear_figure=False, use_container_width=False)

    st.download_button(
        "Download NOAA ensemble spread plot (PNG)",
        data=ens_png,
        file_name="noaa_gefs_wave_ensemble_spread.png",
        mime="image/png",
    )

st.subheader("Combined forecast table")
st.caption(
    "One row per timestamp. Each source keeps its own native time resolution, so some cells may be empty "
    "where a given source has no value at that exact timestamp."
)

display_df = combined_df.copy()
display_df["time"] = pd.to_datetime(display_df["time"]).dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(display_df, use_container_width=True, hide_index=True)

csv_bytes = combined_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download combined table (CSV)",
    data=csv_bytes,
    file_name="multi_source_wave_forecast.csv",
    mime="text/csv",
)

st.subheader("Data sources and licence")

st.markdown(
    """
- **Copernicus Marine** - Mediterranean Sea Waves Analysis and Forecast, product ID `MEDSEA_ANALYSISFORECAST_WAV_006_017`,
  DOI: `10.48670/mds-00373`. Source: European Union, Copernicus Marine Service Information or Data, implemented by
  Mercator Ocean International. Use of Copernicus Marine information remains subject to the Copernicus Marine
  licence and terms of service.
- **NOAA GEFS-Wave ensemble** - global 31-member wave ensemble operated by NOAA/NCEP, accessed directly from NOAA's
  NOMADS GRIB feed.
- **Open-Meteo Marine** - free for non-commercial use, aggregates NOAA GFS-Wave, DWD ICON-Wave, and ECMWF WAM.
"""
)

st.info(
    "This comparison is intended for scientific exploration and cross-checking forecast agreement between models. "
    "It is not a substitute for site-specific engineering analysis or operational coastal-risk decisions."
)
