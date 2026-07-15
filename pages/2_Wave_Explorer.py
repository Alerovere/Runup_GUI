import pandas as pd
import streamlit as st

from src.copernicus_wave_climate import REGIONS, fetch_copernicus_wave_climate_timeseries
from src.extremes import (
    build_return_value_table,
    extract_storm_maxima,
    filter_by_sector,
    summarize_wave_series,
)
from src.plotting import (
    fig_to_png_bytes,
    plot_return_values,
    plot_wave_climate_timeseries,
    plot_wave_rose,
)

st.title("Wave Explorer")

st.info(
    "Use this page to explore the long-term wave climate at a single offshore point, using either the "
    "Mediterranean or the global Copernicus Marine wave reanalysis. You can inspect the directional "
    "distribution, filter by sector, and estimate return values of significant wave height. "
    "If you are unsure what Hs/Tp scenario to use on the Manual calculator page, the \"Suggested scenario\" "
    "section at the bottom of this page can send a return-period estimate straight there."
)

st.markdown(
    """
This page uses a **single-point historical wave time series** from a Copernicus Marine reanalysis.
Choose a point that is **reasonably offshore**, so that it represents open-water forcing rather than a shoreline or harbour grid cell.

The directional sector selector is applied to the extreme-value analysis, so return values and the top-swells table can be explored for specific incoming wave sectors.
"""
)

with st.sidebar:
    st.header("Wave Explorer inputs")

    region_name = st.selectbox(
        "Reanalysis region",
        list(REGIONS.keys()),
        help=(
            "Mediterranean: Copernicus Marine Mediterranean Sea Waves Reanalysis (1/24 deg, hourly). "
            "Global: Copernicus Marine Global Ocean Waves Reanalysis / WAVERYS (0.2 deg, 3-hourly)."
        ),
    )
    region = REGIONS[region_name]

    start_date = st.date_input(
        "Start date",
        value=region["coverage_start"],
        min_value=region["coverage_start"],
        max_value=region["coverage_end"],
        help=f"Beginning of the historical wave time series. The {region_name} reanalysis starts {region['coverage_start'].isoformat()}.",
    )

    end_date = st.date_input(
        "End date",
        value=region["coverage_end"],
        min_value=region["coverage_start"],
        max_value=region["coverage_end"],
        help=(
            f"End of the historical wave time series. The {region_name} reanalysis is periodically extended; "
            f"data should be available at least through {region['coverage_end'].isoformat()}, possibly later."
        ),
    )

    sector_name = st.selectbox(
        "Directional sector",
        [
            "All directions",
            "N", "NE", "E", "SE", "S", "SW", "W", "NW",
        ],
        help="Filter the time series by wave direction before return-value estimation and storm ranking.",
    )

    storm_quantile = st.slider(
        "Storm threshold quantile for Hs",
        min_value=0.90,
        max_value=0.99,
        value=0.95,
        step=0.01,
        help="Hs quantile used to identify storm events before extracting independent storm maxima.",
    )

    min_separation_hours = st.number_input(
        "Minimum separation between storms [hours]",
        min_value=12,
        max_value=120,
        value=48,
        step=6,
        help="Minimum time separation used to decluster independent storm events.",
    )

    return_periods = st.multiselect(
        "Return periods to display [years]",
        [1, 2, 5, 10, 20, 50, 100],
        default=[1, 5, 10, 20, 50, 100],
        help="Return periods used for Hs return-value estimation with a Gumbel fit to storm maxima.",
    )

    fetch_button = st.button(
        "Fetch wave climate",
        type="primary",
        use_container_width=True,
    )

if "wave_explorer_lat" not in st.session_state:
    st.session_state.wave_explorer_lat = 44.046833
if "wave_explorer_lon" not in st.session_state:
    st.session_state.wave_explorer_lon = 8.389593

st.subheader("Point coordinates")
st.caption("These coordinates define the offshore point from which the historical wave climate is extracted.")

col1, col2 = st.columns(2)
with col1:
    st.session_state.wave_explorer_lat = st.number_input(
        "Latitude [deg]",
        value=float(st.session_state.wave_explorer_lat),
        format="%.5f",
        key="wave_explorer_lat_input",
        help="Latitude of the offshore wave-climate point.",
    )
with col2:
    st.session_state.wave_explorer_lon = st.number_input(
        "Longitude [deg]",
        value=float(st.session_state.wave_explorer_lon),
        format="%.5f",
        key="wave_explorer_lon_input",
        help="Longitude of the offshore wave-climate point.",
    )

st.caption(
    f"Selected coordinates: lat = {st.session_state.wave_explorer_lat:.5f}, "
    f"lon = {st.session_state.wave_explorer_lon:.5f}"
)

min_lat, max_lat, min_lon, max_lon = region["bbox"]
if not (min_lat <= st.session_state.wave_explorer_lat <= max_lat and min_lon <= st.session_state.wave_explorer_lon <= max_lon):
    st.warning(
        f"These coordinates fall outside the {region_name} reanalysis domain "
        f"(lat {min_lat} to {max_lat}, lon {min_lon} to {max_lon}). Double-check the point, or switch region."
    )

st.subheader("Map preview")
st.caption("The map is shown for confirmation only. Update the coordinate fields above to move the analysis point.")

map_df = pd.DataFrame(
    {
        "lat": [st.session_state.wave_explorer_lat],
        "lon": [st.session_state.wave_explorer_lon],
    }
)
st.map(map_df, zoom=6, use_container_width=True)

if not fetch_button:
    st.info("Enter an offshore point, choose a region and time range, and click Fetch wave climate.")
    st.stop()

if start_date >= end_date:
    st.error("End date must be later than start date.")
    st.stop()

if not return_periods:
    st.error("Select at least one return period.")
    st.stop()

username = st.secrets.get("COPERNICUSMARINE_USERNAME") or st.secrets.get("COPERNICUS_USERNAME")
password = st.secrets.get("COPERNICUSMARINE_PASSWORD") or st.secrets.get("COPERNICUS_PASSWORD")

if not username or not password:
    st.error("Copernicus credentials are missing in Streamlit secrets.")
    st.stop()

with st.spinner(f"Downloading {region_name} historical wave time series..."):
    climate_df, metadata = fetch_copernicus_wave_climate_timeseries(
        longitude=st.session_state.wave_explorer_lon,
        latitude=st.session_state.wave_explorer_lat,
        start_date=start_date,
        end_date=end_date,
        username=username,
        password=password,
        dataset_id=region["dataset_id"],
    )

sector_df = filter_by_sector(climate_df, sector_name)

if sector_df.empty:
    st.warning("No wave data are available in the selected directional sector for this period.")
    st.stop()

stats = summarize_wave_series(climate_df)

st.caption(f"Region: {region_name} ({region['product_name']})")
st.caption(f"Wave reanalysis dataset ID: {metadata['dataset_id']}")
st.caption(
    f"Using variables: Hs = {metadata['hs_var']}, Tp = {metadata['tp_var']}, Direction = {metadata['dir_var']}"
)

st.subheader("Wave climate summary")

st.markdown(
    f"""
**Selected period**
{pd.to_datetime(climate_df['time'].min()).strftime("%A, %B")} {pd.to_datetime(climate_df['time'].min()).day}, {pd.to_datetime(climate_df['time'].min()).year}
to
{pd.to_datetime(climate_df['time'].max()).strftime("%A, %B")} {pd.to_datetime(climate_df['time'].max()).day}, {pd.to_datetime(climate_df['time'].max()).year}

**Directional sector used for extremes**
{sector_name}
"""
)

c1, c2, c3 = st.columns(3)
c1.metric("Mean Hs (all data)", f"{stats['mean_hs']:.2f} m")
c2.metric("Max Hs (all data)", f"{stats['max_hs']:.2f} m")
c3.metric("95th percentile Hs", f"{stats['p95_hs']:.2f} m")

st.subheader("Wave rose")
st.caption("The wave rose summarizes the directional distribution of wave occurrence at the selected offshore point.")

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_rose = plot_wave_rose(climate_df)
    rose_png = fig_to_png_bytes(fig_rose)
    st.pyplot(fig_rose, clear_figure=False, use_container_width=False)

st.download_button(
    label="Download wave rose (PNG)",
    data=rose_png,
    file_name="wave_rose.png",
    mime="image/png",
)

st.subheader("Extracted wave time series")
st.caption("This figure shows the historical significant wave height and peak period extracted at the selected point.")

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_ts = plot_wave_climate_timeseries(climate_df)
    ts_png = fig_to_png_bytes(fig_ts)
    st.pyplot(fig_ts, clear_figure=False, use_container_width=False)

st.download_button(
    label="Download wave time-series plot (PNG)",
    data=ts_png,
    file_name="wave_timeseries.png",
    mime="image/png",
)

st.subheader("Return values by directional sector")
st.caption(
    "Return values are estimated by fitting a Gumbel distribution to independent storm maxima of Hs within the selected directional sector. "
    "Storms are identified using the selected Hs quantile threshold and declustered with the chosen minimum separation time. "
    "Associated peak periods are derived from the Hs–Tp relationship of the storm-peak events."
)

storm_max_df = extract_storm_maxima(
    sector_df,
    threshold_quantile=float(storm_quantile),
    min_separation_hours=int(min_separation_hours),
)

return_df = build_return_value_table(
    storm_max_df=storm_max_df,
    return_periods=sorted(return_periods),
)

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
with col2:
    fig_ret = plot_return_values(return_df)
    ret_png = fig_to_png_bytes(fig_ret)
    st.pyplot(fig_ret, clear_figure=False, use_container_width=False)

st.download_button(
    label="Download return-value plot (PNG)",
    data=ret_png,
    file_name="wave_return_values.png",
    mime="image/png",
)

st.subheader("Top 10 swells by significant wave height")
st.caption(
    "This table lists the 10 strongest independent storm peaks identified within the selected directional sector and analysis settings."
)

top10_df = (
    storm_max_df.sort_values("Hs [m]", ascending=False)
    .head(10)
    .copy()
    .reset_index(drop=True)
)

top10_df.insert(0, "Rank", range(1, len(top10_df) + 1))
top10_df["Sector"] = sector_name

top10_display = top10_df[["Rank", "time", "Hs [m]", "Tp [s]", "Dir [deg]", "Sector"]].copy()
top10_display["time"] = pd.to_datetime(top10_display["time"]).dt.strftime("%Y-%m-%d %H:%M")
top10_display["Hs [m]"] = top10_display["Hs [m]"].round(3)
top10_display["Tp [s]"] = top10_display["Tp [s]"].round(3)
top10_display["Dir [deg]"] = top10_display["Dir [deg]"].round(1)

st.dataframe(top10_display, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------
# Suggested scenario for the Manual Calculator
# -----------------------------------------------------------------------
st.subheader("Suggested scenario for the Manual calculator")
st.caption(
    "Not sure what Hs/Tp to enter on the Manual calculator page? Pick a return period below to see the "
    "corresponding Hs (from the Gumbel fit above) and its associated Tp (from the Hs-Tp relationship of the "
    "storm peaks), then send them straight to that page. You will still need to enter a beach slope there, "
    "since that is a site property this wave climate analysis cannot estimate."
)

suggested_rp = st.selectbox(
    "Return period [years]",
    sorted(return_df["Return period [years]"].tolist()),
    key="suggested_return_period",
)

suggested_row = return_df.loc[return_df["Return period [years]"] == suggested_rp].iloc[0]
suggested_hs = float(suggested_row["Return Hs [m]"])
suggested_tp = float(suggested_row["Associated Tp [s]"])

s1, s2 = st.columns(2)
s1.metric(f"Hs, {suggested_rp}-year return period", f"{suggested_hs:.2f} m")
s2.metric("Associated Tp", f"{suggested_tp:.2f} s")

if st.button("Use these values in the Manual calculator", type="primary"):
    st.session_state["prefill_hs"] = suggested_hs
    st.session_state["prefill_tp"] = suggested_tp
    st.session_state["prefill_note"] = (
        f"Prefilled from Wave Explorer: {region_name} reanalysis, {sector_name} sector, "
        f"{suggested_rp}-year return period (Hs = {suggested_hs:.2f} m, Tp = {suggested_tp:.2f} s)."
    )
    st.switch_page("pages/1_Manual_Calculator.py")

st.subheader("Data source and licence")
st.markdown(
    f"""
- **{region['product_name']}**, product ID `{region['product_id']}`, DOI: `{region['doi']}`.
"""
)
st.caption(
    "Source: European Union, Copernicus Marine Service Information or Data, implemented by Mercator Ocean International."
)
