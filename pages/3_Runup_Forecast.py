import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src.copernicus_sealevel import (
    MED_SEALEVEL_DATASET_ID,
    fetch_copernicus_sealevel_timeseries,
)
from src.extremes import filter_by_sector
from src.sector_map import build_sector_map
from src.forecast_thresholds import (
    build_daily_exceedance_probability,
    build_exceedance_events,
    build_exceedance_probability_timeseries,
    describe_exceedance_methodology,
    describe_worst_probability,
    summarize_exceedance_probability,
)
from src.multi_source_forecast import (
    GEFS_WAVE_FORECAST_HOURS,
    GEFS_WAVE_MEMBERS,
    MED_WAVE_FORECAST_DATASET_ID,
    build_shared_hourly_grid,
    fetch_copernicus_med_wave_forecast,
    fetch_noaa_gefs_wave_ensemble,
    fetch_openmeteo_wave_forecast,
    interpolate_ensemble_to_hourly,
    interpolate_series_to_grid,
    merge_multi_source,
    summarize_ensemble_detail,
)
from src.plotting import (
    fig_to_png_bytes,
    plot_daily_threshold_bar,
    plot_exceedance_probability_timeseries,
    plot_forecast_band,
    plot_wave_data_comparison,
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

    sector_names = st.multiselect(
        "Directional sector(s)",
        ["All directions", "N", "NE", "E", "SE", "S", "SW", "W", "NW"],
        default=["All directions"],
        help=(
            "Filter the forecast wave data by incoming direction before computing runup, so the risk estimate only "
            "reflects wave energy actually relevant to a site facing these sectors. Selecting several sectors "
            "combines them (wave energy from ANY selected sector counts) - handy for a site exposed to a broad "
            "swell window, e.g. SW + W. \"All directions\" overrides any other selection. Shown as wedge(s) on the "
            "map below."
        ),
    )
    if not sector_names:
        sector_names = ["All directions"]

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
if "All directions" in sector_names:
    st.caption("The map is shown for confirmation only. Update the coordinate fields above to move the forecast point.")
else:
    sector_label = " + ".join(sector_names)
    is_plural = len(sector_names) > 1
    wedge_word = "wedges" if is_plural else "wedge"
    wedge_verb = "show" if is_plural else "shows"
    sector_word = "sectors" if is_plural else "sector"
    st.caption(
        f"The shaded {wedge_word} {wedge_verb} the **{sector_label}** {sector_word} selected in the sidebar - only "
        f"wave energy coming from within {'these wedges' if is_plural else 'this wedge'} is used in the runup "
        "calculation below. Update the coordinate fields above to move the forecast point."
    )

sector_map = build_sector_map(
    st.session_state.runup_forecast_lat,
    st.session_state.runup_forecast_lon,
    sector_name=sector_names,
)
st_folium(sector_map, use_container_width=True, height=400, returned_objects=[])

if fetch_button:
    if not (use_copernicus or use_noaa or use_openmeteo):
        st.error("Select at least one forecast source.")
        st.stop()

    lat = st.session_state.runup_forecast_lat
    lon = st.session_state.runup_forecast_lon

    source_frames_for_wide = {}
    source_wave_frames_for_runup = {}
    source_notes = []
    cop_df_raw = None
    om_df_raw = None
    noaa_detail_df_raw = None
    noaa_metadata = None
    sealevel_df_raw = None
    ssh_var = None

    username = st.secrets.get("COPERNICUSMARINE_USERNAME") or st.secrets.get("COPERNICUS_USERNAME")
    password = st.secrets.get("COPERNICUSMARINE_PASSWORD") or st.secrets.get("COPERNICUS_PASSWORD")

    if use_copernicus:
        if not username or not password:
            st.warning("Copernicus credentials are missing in Streamlit secrets. Skipping this source.")
        else:
            with st.spinner("Downloading Copernicus Marine forecast..."):
                try:
                    cop_df_raw = fetch_copernicus_med_wave_forecast(
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
                noaa_detail_df_raw, _noaa_summary_df_raw, noaa_metadata = fetch_noaa_gefs_wave_ensemble(
                    longitude=lon,
                    latitude=lat,
                    forecast_days=forecast_days,
                )
                source_notes.append(
                    f"NOAA GEFS-Wave ensemble, cycle {noaa_metadata['cycle_date']} {noaa_metadata['cycle_hour']:02d}Z "
                    f"({noaa_metadata['succeeded']}/{noaa_metadata['requested']} member-hour requests succeeded, "
                    "interpolated to hourly resolution per member via cubic spline)"
                )
            except Exception as e:
                st.warning(f"NOAA GEFS-Wave ensemble fetch failed: {e}")

    if use_openmeteo:
        with st.spinner("Downloading Open-Meteo Marine forecast..."):
            try:
                om_df_raw = fetch_openmeteo_wave_forecast(
                    longitude=lon,
                    latitude=lat,
                    forecast_days=forecast_days,
                )
                source_notes.append("Open-Meteo Marine API: `https://marine-api.open-meteo.com/v1/marine`")
            except Exception as e:
                st.warning(f"Open-Meteo Marine fetch failed: {e}")

    if cop_df_raw is None and noaa_detail_df_raw is None and om_df_raw is None:
        st.error("None of the selected sources returned data for this point. Try a different location or fewer sources.")
        st.stop()

    if water_level_mode == "Copernicus mean-removed sea-level signal":
        if not username or not password:
            st.warning("Copernicus credentials are missing in Streamlit secrets. Falling back to eta = 0.")
        else:
            with st.spinner("Downloading Copernicus sea-level signal..."):
                try:
                    sealevel_df_raw, ssh_var = fetch_copernicus_sealevel_timeseries(
                        longitude=lon,
                        latitude=lat,
                        username=username,
                        password=password,
                        forecast_days=forecast_days,
                    )
                except Exception as e:
                    st.warning(f"Copernicus sea-level fetch failed: {e}. Falling back to eta = 0.")

    # Copernicus and Open-Meteo are both hourly but not guaranteed to land on exactly
    # the same timestamps, and NOAA is only every 6 hours. Spline-interpolate every
    # source (and the sea-level signal, if used) onto one shared hourly grid so
    # everything downstream - the combined table, the wave-data plot, and the runup
    # band - lines up on identical timestamps.
    shared_grid = build_shared_hourly_grid([cop_df_raw, om_df_raw, noaa_detail_df_raw, sealevel_df_raw])

    cop_df = interpolate_series_to_grid(cop_df_raw, shared_grid) if cop_df_raw is not None else None
    om_df = interpolate_series_to_grid(om_df_raw, shared_grid) if om_df_raw is not None else None
    noaa_detail_df = (
        interpolate_ensemble_to_hourly(noaa_detail_df_raw, freq="1h", time_grid=shared_grid)
        if noaa_detail_df_raw is not None
        else None
    )
    sealevel_df = (
        interpolate_series_to_grid(
            sealevel_df_raw, shared_grid, value_cols=("sea-level signal [m]",), circular_cols=()
        )
        if sealevel_df_raw is not None
        else None
    )

    if cop_df is not None and not cop_df.empty:
        source_frames_for_wide["Copernicus"] = cop_df
        source_wave_frames_for_runup["Copernicus"] = cop_df
    if om_df is not None and not om_df.empty:
        source_frames_for_wide["Open-Meteo"] = om_df
        source_wave_frames_for_runup["Open-Meteo"] = om_df
    if noaa_detail_df is not None and not noaa_detail_df.empty:
        noaa_summary_df = summarize_ensemble_detail(noaa_detail_df)
        source_frames_for_wide["NOAA GEFS-Wave"] = noaa_summary_df[["time", "Hs [m]", "Tp [s]", "Dir [deg]"]]

    if not source_frames_for_wide:
        st.error("None of the selected sources returned data for this point. Try a different location or fewer sources.")
        st.stop()

    # The "Wave data" plot and combined table always show the full, unfiltered wave
    # climate for context. If one or more directional sectors are selected, only wave
    # energy from those sectors (OR-combined) should count toward the runup/TWL risk,
    # so build sector-filtered copies of the same source frames here and feed ONLY
    # those into the runup calc.
    source_wave_frames_for_runup_calc = {
        name: filter_by_sector(df, sector_names) for name, df in source_wave_frames_for_runup.items()
    }
    noaa_detail_df_for_runup_calc = (
        filter_by_sector(noaa_detail_df, sector_names) if noaa_detail_df is not None and not noaa_detail_df.empty else None
    )

    with st.spinner("Running empirical runup models against every source..."):
        runup_detail_df = compute_multi_source_runup_detail(
            source_wave_frames=source_wave_frames_for_runup_calc,
            slope=float(slope),
            water_level_mode=water_level_mode,
            constant_eta=float(constant_eta),
            sealevel_df=sealevel_df,
            noaa_detail_df=noaa_detail_df_for_runup_calc,
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
    st.session_state["rf_source_wave_frames_for_runup"] = source_wave_frames_for_runup
    st.session_state["rf_source_notes"] = source_notes
    st.session_state["rf_noaa_detail_df"] = noaa_detail_df
    st.session_state["rf_sealevel_df"] = sealevel_df
    st.session_state["rf_water_level_mode"] = water_level_mode
    st.session_state["rf_constant_eta"] = float(constant_eta)
    st.session_state["rf_ssh_var"] = ssh_var
    st.session_state["rf_sector_names"] = sector_names

if "rf_combined_wide_df" not in st.session_state:
    st.info("Enter an offshore point, choose which sources to include, and click Fetch runup forecast.")
    st.stop()

combined_wide_df = st.session_state["rf_combined_wide_df"]
runup_detail_df = st.session_state["rf_runup_detail_df"]
envelope_df = st.session_state["rf_envelope_df"]
source_frames_for_wide = st.session_state["rf_source_frames_for_wide"]
source_wave_frames_for_runup = st.session_state["rf_source_wave_frames_for_runup"]
source_notes = st.session_state["rf_source_notes"]
noaa_detail_df = st.session_state["rf_noaa_detail_df"]
sealevel_df = st.session_state["rf_sealevel_df"]
water_level_mode = st.session_state["rf_water_level_mode"]
constant_eta = st.session_state["rf_constant_eta"]
# threshold/threshold_enabled are intentionally NOT cached in session_state: unlike the
# fetched forecast data, the threshold is just a comparison line applied at display time
# (it's never baked into runup_detail_df), so reading it live from the sidebar lets a
# manager adjust it and immediately see the updated exceedance probability without
# re-running the (slow) fetch + runup-model computation.
ssh_var = st.session_state["rf_ssh_var"]
# sector_names IS cached (unlike threshold): it's baked into runup_detail_df at fetch
# time (the sector filter is applied before the runup models run), so the sidebar
# multiselect value must not be read live here - that would mislabel the caption below
# with sector(s) that weren't actually used for the displayed results.
sector_names = st.session_state["rf_sector_names"]

st.subheader("Sources used")
for note in source_notes:
    st.caption(note)
if water_level_mode == "Copernicus mean-removed sea-level signal" and ssh_var:
    st.caption(f"Sea-level dataset ID: `{MED_SEALEVEL_DATASET_ID}` (variable: {ssh_var})")

show_twl = water_level_mode == "Copernicus mean-removed sea-level signal" or abs(constant_eta) > 0

st.subheader("Forecast summary")

mean_runup = float(envelope_df["runup_mean"].mean())
max_runup = float(envelope_df["runup_max"].max())

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

st.subheader("Wave data")
wave_data_caption = (
    "Significant wave height and peak period through the forecast period, all sources interpolated onto the same "
    "hourly grid. Copernicus and Open-Meteo are drawn as solid lines (single deterministic series). NOAA GEFS-Wave "
    "has 31 members, so it is instead drawn as its ensemble mean with 25th-75th and 5th-95th percentile shaded bands."
)
if water_level_mode == "Copernicus mean-removed sea-level signal" and sealevel_df is not None and not sealevel_df.empty:
    wave_data_caption += " The bottom panel shows the Copernicus mean-removed sea-level signal used for total water level, on the same time axis."
st.caption(wave_data_caption)

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    show_sealevel_panel = (
        water_level_mode == "Copernicus mean-removed sea-level signal"
        and sealevel_df is not None
        and not sealevel_df.empty
    )
    fig_wave = plot_wave_data_comparison(
        source_wave_frames_for_runup,
        noaa_detail_df,
        sealevel_df=sealevel_df if show_sealevel_panel else None,
    )
    wave_png = fig_to_png_bytes(fig_wave)
    st.pyplot(fig_wave, clear_figure=False, use_container_width=False)

st.download_button(
    "Download wave data plot (PNG)",
    data=wave_png,
    file_name="wave_data_comparison.png",
    mime="image/png",
)

plot_value_col = "Total water level [m]" if show_twl else "Runup [m]"
plot_title = "Combined forecast total water level (all sources x all models)" if show_twl else "Combined forecast runup (all sources x all models)"

st.subheader("Runup forecast")
runup_caption = (
    "The dark blue line is the combined mean across every selected source, runup model, and (for NOAA) ensemble "
    "member. The shaded bands are the 25th-75th and 5th-95th percentiles (rather than mean ± SD, so the band can "
    "never fall outside the actual min/max), and the thin blue lines trace the overall min/max envelope. The red "
    "dashed line marks the critical elevation threshold, if enabled."
)
if "All directions" not in sector_names:
    sector_label = " + ".join(sector_names)
    sector_word = "sectors" if len(sector_names) > 1 else "sector"
    runup_caption += (
        f" Only wave energy from the **{sector_label}** {sector_word} (selected in the sidebar at fetch time) feeds "
        f"into this calculation, so hours where waves were coming from outside {'those sectors' if len(sector_names) > 1 else 'that sector'} "
        "may be missing here even though they still appear in the Wave data plot above."
    )
st.caption(runup_caption)

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_band = plot_forecast_band(
        detail_df=runup_detail_df,
        value_col=plot_value_col,
        threshold=threshold,
        title=plot_title,
    )
    band_png = fig_to_png_bytes(fig_band)
    st.pyplot(fig_band, clear_figure=False, use_container_width=False)

st.download_button(
    label="Download runup forecast plot (PNG)",
    data=band_png,
    file_name="runup_forecast.png",
    mime="image/png",
)

if threshold is not None:
    compare_value_col = "Total water level [m]" if show_twl else "Runup [m]"
    compare_label = "total water level" if show_twl else "runup"
    alert_probability = 0.5

    prob_ts_df = build_exceedance_probability_timeseries(
        detail_df=runup_detail_df,
        value_col=compare_value_col,
        threshold=float(threshold),
    )

    daily_prob_df = build_daily_exceedance_probability(prob_ts_df)
    prob_summary = summarize_exceedance_probability(prob_ts_df, alert_probability=alert_probability)

    st.subheader("Daily threshold status")
    st.caption(
        "Probability that forecast {label} exceeds the threshold, computed as the fraction of each source's own "
        "estimates (runup models, and for NOAA, ensemble members) above the threshold at each timestep, averaged "
        "with equal weight across the selected sources. Bar height/color show each day's peak probability.".format(
            label=compare_label
        )
    )

    col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
    with col2:
        fig_daily = plot_daily_threshold_bar(
            daily_prob_df,
            title=f"Daily threshold exceedance probability for forecast {compare_label}",
        )
        daily_png = fig_to_png_bytes(fig_daily)
        st.pyplot(fig_daily, clear_figure=False, use_container_width=False)

    st.download_button(
        "Download daily threshold status (PNG)",
        data=daily_png,
        file_name="daily_threshold_status.png",
        mime="image/png",
    )

    st.markdown(describe_exceedance_methodology(compare_label, float(threshold)))

    st.markdown(
        f"<div style='padding:0.6rem 0.8rem;border-radius:0.5rem;background:{prob_summary['worst_color']};color:white;font-weight:600;'>{describe_worst_probability(prob_summary['worst_probability'], prob_summary['worst_category'], float(threshold), compare_label)}</div>",
        unsafe_allow_html=True,
    )

    st.caption(f"Hourly detail - where within the forecast the probability actually peaks (alert level shown at {alert_probability:.0%}):")
    col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
    with col2:
        fig_prob_ts = plot_exceedance_probability_timeseries(
            prob_ts_df,
            alert_probability=alert_probability,
            title=f"Hourly exceedance probability for forecast {compare_label}",
        )
        prob_ts_png = fig_to_png_bytes(fig_prob_ts)
        st.pyplot(fig_prob_ts, clear_figure=False, use_container_width=False)

    st.download_button(
        "Download hourly exceedance probability plot (PNG)",
        data=prob_ts_png,
        file_name="exceedance_probability_timeseries.png",
        mime="image/png",
    )

    exceedance_events_df = build_exceedance_events(prob_ts_df, alert_probability=alert_probability)
    if not exceedance_events_df.empty:
        st.caption(f"When the exceedance probability is at or above the {alert_probability:.0%} alert level:")
        display_events_df = exceedance_events_df.copy()
        display_events_df["Start"] = pd.to_datetime(display_events_df["Start"]).dt.strftime("%Y-%m-%d %H:%M")
        display_events_df["End"] = pd.to_datetime(display_events_df["End"]).dt.strftime("%Y-%m-%d %H:%M")
        display_events_df = display_events_df.rename(columns={"Start": "Start (UTC)", "End": "End (UTC)"})
        st.dataframe(display_events_df, use_container_width=True, hide_index=True)
    else:
        st.caption(f"The exceedance probability never reaches the {alert_probability:.0%} alert level in this forecast.")

st.subheader("Combined forecast table")
st.caption(
    "One row per timestamp: each source's Hs/Tp/Dir side-by-side, plus the combined runup / total-water-level "
    "min-mean-max across every source, runup model, and ensemble member. Some cells may be empty where a given "
    "source has no value at that exact timestamp."
)

display_df = combined_wide_df.copy()
display_df["time"] = pd.to_datetime(display_df["time"]).dt.strftime("%Y-%m-%d %H:%M")
display_df = display_df.rename(columns={"time": "time (UTC)"})
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
