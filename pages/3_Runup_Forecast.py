import pandas as pd
import streamlit as st

from src.copernicus_sealevel import (
    MED_SEALEVEL_DATASET_ID,
    fetch_copernicus_sealevel_timeseries,
)
from src.forecast_thresholds import (
    build_daily_threshold_status,
    build_threshold_timeseries,
    describe_threshold_logic,
    describe_worst_status,
    summarize_threshold_status,
)
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
    plot_daily_threshold_bar,
    plot_forecast_model_timeseries,
    plot_multi_source_hs_comparison,
)
from src.runup_forecast import build_runup_envelope, compute_multi_source_runup_detail

st.title("Runup Forecast")

st.info(
    "Use this page to compare independent wave forecasts at a single offshore point and turn all of them into "
    "a combined runup / total water level forecast in one place. Every empirical runup model in py-wave-runup "
    "is run against every selected source (and, for NOAA, against every individual ensemble member), so the "
    "resulting band reflects both forecast-source disagreement and empirical-model disagreement together."
)

st.markdown(
    """
Sources compared on this page:

- **Copernicus Marine** - Mediterranean Sea Waves Analysis and Forecast
- **NOAA GEFS-Wave ensemble** - all 31 members (1 control + 30 perturbed) of NOAA's global wave ensemble, pulled directly
  from NOAA's GRIB feed. Noticeably slower than the other two (roughly 1-3 minutes), and every member is run through
  every runup model individually, so it also tends to dominate the width of the combined runup band.
- **Open-Meteo Marine** - free aggregator of several global wave models (no account needed)

Enter a point that is **reasonably offshore**, rather than directly on the shoreline, to avoid land grid cells.
"""
)

with st.sidebar:
    st.header("Runup forecast inputs")

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
            "Use a constant still-water-level offset, or use Copernicus Mediterranean modelled sea surface height "
            "after removing the mean over the downloaded period. The sea-level signal is applied identically on "
            "top of every selected wave source."
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
            "then centered by subtracting the mean over the downloaded period. Only valid within the Mediterranean domain."
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
            help="Critical elevation used to interpret exceedance of forecast values.",
        )

    fetch_button = st.button(
        "Fetch runup forecast",
        type="primary",
        use_container_width=True,
    )

if "runup_forecast_lat" not in st.session_state:
    st.session_state.runup_forecast_lat = 44.046833
if "runup_forecast_lon" not in st.session_state:
    st.session_state.runup_forecast_lon = 8.389593

st.subheader("Forecast point coordinates")
st.caption("These coordinates define the offshore point from which all forecasts are extracted.")

col1, col2 = st.columns(2)
with col1:
    st.session_state.runup_forecast_lat = st.number_input(
        "Latitude [deg]",
        value=float(st.session_state.runup_forecast_lat),
        format="%.5f",
        key="runup_forecast_lat_input",
        help="Latitude of the offshore forecast point.",
    )
with col2:
    st.session_state.runup_forecast_lon = st.number_input(
        "Longitude [deg]",
        value=float(st.session_state.runup_forecast_lon),
        format="%.5f",
        key="runup_forecast_lon_input",
        help="Longitude of the offshore forecast point.",
    )

st.caption(
    f"Selected coordinates: lat = {st.session_state.runup_forecast_lat:.5f}, "
    f"lon = {st.session_state.runup_forecast_lon:.5f}"
)

st.subheader("Map preview")
st.caption("The map is shown for confirmation only. Update the coordinate fields above to move the forecast point.")

map_df = pd.DataFrame(
    {
        "lat": [st.session_state.runup_forecast_lat],
        "lon": [st.session_state.runup_forecast_lon],
    }
)
st.map(map_df, zoom=6, use_container_width=True)

if fetch_button:
    if not (use_copernicus or use_noaa or use_openmeteo):
        st.error("Select at least one forecast source.")
        st.stop()

    lat = st.session_state.runup_forecast_lat
    lon = st.session_state.runup_forecast_lon

    source_frames_for_wide = {}
    source_wave_frames_for_runup = {}
    source_notes = []
    noaa_detail_df = None
    noaa_metadata = None
    sealevel_df = None
    ssh_var = None

    username = st.secrets.get("COPERNICUSMARINE_USERNAME") or st.secrets.get("COPERNICUS_USERNAME")
    password = st.secrets.get("COPERNICUSMARINE_PASSWORD") or st.secrets.get("COPERNICUS_PASSWORD")

    if use_copernicus:
        if not username or not password:
            st.warning("Copernicus credentials are missing in Streamlit secrets. Skipping this source.")
        else:
            with st.spinner("Downloading Copernicus Marine forecast..."):
                try:
                    cop_df = fetch_copernicus_med_wave_forecast(
                        longitude=lon,
                        latitude=lat,
                        username=username,
                        password=password,
                        forecast_days=forecast_days,
                    )
                    source_frames_for_wide["Copernicus"] = cop_df
                    source_wave_frames_for_runup["Copernicus"] = cop_df
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
                source_frames_for_wide["NOAA GEFS-Wave"] = noaa_summary_df[["time", "Hs [m]", "Tp [s]", "Dir [deg]"]]
                source_notes.append(
                    f"NOAA GEFS-Wave ensemble, cycle {noaa_metadata['cycle_date']} {noaa_metadata['cycle_hour']:02d}Z "
                    f"({noaa_metadata['succeeded']}/{noaa_metadata['requested']} member-hour requests succeeded)"
                )
            except Exception as e:
                st.warning(f"NOAA GEFS-Wave ensemble fetch failed: {e}")

    if use_openmeteo:
        with st.spinner("Downloading Open-Meteo Marine forecast..."):
            try:
                om_df = fetch_openmeteo_wave_forecast(
                    longitude=lon,
                    latitude=lat,
                    forecast_days=forecast_days,
                )
                source_frames_for_wide["Open-Meteo"] = om_df
                source_wave_frames_for_runup["Open-Meteo"] = om_df
                source_notes.append("Open-Meteo Marine API: `https://marine-api.open-meteo.com/v1/marine`")
            except Exception as e:
                st.warning(f"Open-Meteo Marine fetch failed: {e}")

    if not source_frames_for_wide:
        st.error("None of the selected sources returned data for this point. Try a different location or fewer sources.")
        st.stop()

    if water_level_mode == "Copernicus mean-removed sea-level signal":
        if not username or not password:
            st.warning("Copernicus credentials are missing in Streamlit secrets. Falling back to eta = 0.")
        else:
            with st.spinner("Downloading Copernicus sea-level signal..."):
                try:
                    sealevel_df, ssh_var = fetch_copernicus_sealevel_timeseries(
                        longitude=lon,
                        latitude=lat,
                        username=username,
                        password=password,
                    )
                except Exception as e:
                    st.warning(f"Copernicus sea-level fetch failed: {e}. Falling back to eta = 0.")

    with st.spinner("Running empirical runup models against every source..."):
        runup_detail_df = compute_multi_source_runup_detail(
            source_wave_frames=source_wave_frames_for_runup,
            slope=float(slope),
            water_level_mode=water_level_mode,
            constant_eta=float(constant_eta),
            sealevel_df=sealevel_df,
            noaa_detail_df=noaa_detail_df,
        )

    if runup_detail_df.empty:
        st.warning("No runup results were computed from the fetched forecast data.")
        st.stop()

    envelope_df = build_runup_envelope(runup_detail_df)

    combined_wide_df = merge_multi_source(source_frames_for_wide)
    combined_wide_df = combined_wide_df.merge(envelope_df, on="time", how="left")

    st.session_state["rf_combined_wide_df"] = combined_wide_df
    st.session_state["rf_runup_detail_df"] = runup_detail_df
    st.session_state["rf_envelope_df"] = envelope_df
    st.session_state["rf_source_frames_for_wide"] = source_frames_for_wide
    st.session_state["rf_source_notes"] = source_notes
    st.session_state["rf_noaa_detail_df"] = noaa_detail_df
    st.session_state["rf_water_level_mode"] = water_level_mode
    st.session_state["rf_constant_eta"] = float(constant_eta)
    st.session_state["rf_threshold"] = float(threshold) if threshold is not None else None
    st.session_state["rf_ssh_var"] = ssh_var

if "rf_combined_wide_df" not in st.session_state:
    st.info("Enter an offshore point, choose which sources to include, and click Fetch runup forecast.")
    st.stop()

combined_wide_df = st.session_state["rf_combined_wide_df"]
runup_detail_df = st.session_state["rf_runup_detail_df"]
envelope_df = st.session_state["rf_envelope_df"]
source_frames_for_wide = st.session_state["rf_source_frames_for_wide"]
source_notes = st.session_state["rf_source_notes"]
noaa_detail_df = st.session_state["rf_noaa_detail_df"]
water_level_mode = st.session_state["rf_water_level_mode"]
constant_eta = st.session_state["rf_constant_eta"]
threshold = st.session_state["rf_threshold"]
ssh_var = st.session_state["rf_ssh_var"]

st.subheader("Sources used")
for note in source_notes:
    st.caption(note)
if water_level_mode == "Copernicus mean-removed sea-level signal" and ssh_var:
    st.caption(f"Sea-level dataset ID: `{MED_SEALEVEL_DATASET_ID}` (variable: {ssh_var})")

show_twl = water_level_mode == "Copernicus mean-removed sea-level signal" or abs(constant_eta) > 0

st.subheader("Forecast summary")

max_hs_records = []
for name, df in source_frames_for_wide.items():
    if df is None or df.empty:
        continue
    idx = df["Hs [m]"].idxmax()
    row = df.loc[idx]
    max_hs_records.append(
        {
            "Source": name,
            "Hs [m]": float(row["Hs [m]"]),
            "Tp [s]": float(row["Tp [s]"]),
            "time": pd.to_datetime(row["time"]),
        }
    )
max_hs_df = pd.DataFrame(max_hs_records)

mean_runup = float(envelope_df["runup_mean"].mean())
max_runup = float(envelope_df["runup_max"].max())

if not max_hs_df.empty:
    top_row = max_hs_df.loc[max_hs_df["Hs [m]"].idxmax()]
    st.markdown(
        f"""
**Maximum forecast wave conditions (across selected sources)**
Hs max = **{top_row["Hs [m]"]:.2f} m** ({top_row["Source"]})
Associated peak period = **{top_row["Tp [s]"]:.2f} s**
Expected on **{top_row["time"].strftime("%A, %B")} {top_row["time"].day}, {top_row["time"].year}**
"""
    )

c1, c2 = st.columns(2)
c1.metric("Mean runup (combined)", f"{mean_runup:.2f} m")
c2.metric("Maximum runup (combined)", f"{max_runup:.2f} m")

if show_twl:
    mean_twl = float(envelope_df["twl_mean"].mean())
    max_twl = float(envelope_df["twl_max"].max())
    c3, c4 = st.columns(2)
    c3.metric("Mean TWL (combined)", f"{mean_twl:.2f} m")
    c4.metric("Maximum TWL (combined)", f"{max_twl:.2f} m")

if water_level_mode == "Copernicus mean-removed sea-level signal":
    st.caption(
        "Total water level is computed using a Copernicus Mediterranean modelled sea-level signal, applied identically "
        "on top of every source. This is not a local tide-gauge prediction."
    )
elif abs(constant_eta) > 0:
    st.caption(f"Total water level is computed using a constant user-defined water-level offset of {constant_eta:.2f} m.")
else:
    st.caption("Only runup is evaluated here, because no additional water-level offset has been applied.")

st.caption(
    f"The combined runup band below pools {int(envelope_df['n_estimates'].max())} runup estimates at the busiest "
    "timestep (every selected source x every empirical runup model x, for NOAA, every ensemble member)."
)

st.subheader("Hs comparison")
st.caption(
    "Significant wave height through the forecast period, one line per source. "
    "For NOAA, this line is the GEFS-Wave ensemble mean."
)

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_hs = plot_multi_source_hs_comparison(combined_wide_df, list(source_frames_for_wide.keys()))
    hs_png = fig_to_png_bytes(fig_hs)
    st.pyplot(fig_hs, clear_figure=False, use_container_width=False)

st.download_button(
    "Download Hs comparison plot (PNG)",
    data=hs_png,
    file_name="multi_source_hs_comparison.png",
    mime="image/png",
)

if threshold is not None:
    compare_value_col = "Total water level [m]" if show_twl else "Runup [m]"
    compare_label = "total water level" if show_twl else "runup"

    threshold_ts_df = build_threshold_timeseries(
        detail_df=runup_detail_df,
        value_col=compare_value_col,
        threshold=float(threshold),
    )

    daily_status_df = build_daily_threshold_status(threshold_ts_df)
    threshold_summary = summarize_threshold_status(threshold_ts_df)

    st.subheader("Daily threshold status")
    st.caption(
        "This chart summarizes the worst threshold class reached on each forecast day, combining every selected "
        "source, runup model, and (for NOAA) ensemble member at each timestep."
    )

    col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
    with col2:
        fig_daily = plot_daily_threshold_bar(
            daily_status_df,
            title=f"Daily threshold status for forecast {compare_label}",
        )
        daily_png = fig_to_png_bytes(fig_daily)
        st.pyplot(fig_daily, clear_figure=False, use_container_width=False)

    st.download_button(
        "Download daily threshold status (PNG)",
        data=daily_png,
        file_name="daily_threshold_status.png",
        mime="image/png",
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

plot_value_col = "Total water level [m]" if show_twl else "Runup [m]"
plot_title = "Combined forecast total water level (all sources x all models)" if show_twl else "Combined forecast runup (all sources x all models)"

st.subheader("Runup forecast band")
st.caption(
    "Each thin gray dotted line is one (source, runup model, ensemble member) combination. The dark blue line is the "
    "combined mean, the shaded band is the mean ± 1 standard deviation, and the red dashed line marks the critical "
    "elevation threshold, if enabled."
)

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_band = plot_forecast_model_timeseries(
        detail_df=runup_detail_df,
        value_col=plot_value_col,
        threshold=threshold,
        title=plot_title,
    )
    band_png = fig_to_png_bytes(fig_band)
    st.pyplot(fig_band, clear_figure=False, use_container_width=False)

st.download_button(
    label="Download runup forecast band (PNG)",
    data=band_png,
    file_name="runup_forecast_band.png",
    mime="image/png",
)

if noaa_detail_df is not None and not noaa_detail_df.empty:
    with st.expander("NOAA GEFS-Wave ensemble Hs spread (optional detail)"):
        st.caption(
            "Each light gray dotted line is one of the 31 ensemble members' Hs. The dark blue line is the ensemble "
            "mean, and the shaded band is the mean ± 1 standard deviation across members."
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
    "One row per timestamp: each source's Hs/Tp/Dir side-by-side, plus the combined runup / total-water-level "
    "min-mean-max across every source, runup model, and ensemble member. Some cells may be empty where a given "
    "source has no value at that exact timestamp."
)

display_df = combined_wide_df.copy()
display_df["time"] = pd.to_datetime(display_df["time"]).dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(display_df, use_container_width=True, hide_index=True)

csv_bytes = combined_wide_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download combined table (CSV)",
    data=csv_bytes,
    file_name="runup_forecast_combined.csv",
    mime="text/csv",
)

st.subheader("Data sources and licence")

st.markdown(
    """
- **Copernicus Marine** - Mediterranean Sea Waves Analysis and Forecast, product ID `MEDSEA_ANALYSISFORECAST_WAV_006_017`,
  DOI: `10.48670/mds-00373`. When the Copernicus sea-level signal is used, also Mediterranean Sea Physics Analysis and
  Forecast, product ID `MEDSEA_ANALYSISFORECAST_PHY_006_013`, DOI: `10.48670/mds-00359`. Source: European Union,
  Copernicus Marine Service Information or Data, implemented by Mercator Ocean International. Use of Copernicus Marine
  information remains subject to the Copernicus Marine licence and terms of service.
- **NOAA GEFS-Wave ensemble** - global 31-member wave ensemble operated by NOAA/NCEP, accessed directly from NOAA's
  NOMADS GRIB feed.
- **Open-Meteo Marine** - free for non-commercial use, aggregates NOAA GFS-Wave, DWD ICON-Wave, and ECMWF WAM.
"""
)

st.info(
    "This comparison is intended for scientific exploration and cross-checking forecast agreement between models and "
    "sources. It is not a substitute for site-specific engineering analysis or operational coastal-risk decisions."
)
