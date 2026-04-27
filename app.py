import streamlit as st

st.set_page_config(
    page_title="Wave Runup and TWL Calculator",
    layout="wide",
)

st.title("Wave Runup and Total Water Level Calculator")

st.markdown(
    """
This application is a scientific and educational tool for exploring **wave runup** and **total water level (TWL)** on beaches.

Wave runup is the uprush of water above the still water level on a beach or coastal slope.  
During energetic conditions, the elevation reached at the shoreline depends not only on the waves themselves,
but also on the background water level. That combined signal is often what matters most when thinking about
coastal flooding, overtopping, or the possible inundation of low-lying infrastructure.
"""
)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image(
        "https://media.springernature.com/full/springer-static/image/art%3A10.1038%2Fs41598-017-01362-7/MediaObjects/41598_2017_1362_Fig1_HTML.jpg?as=webp",
        caption=(
            "Conceptual components of coastal water levels. "
            "Figure from Vitousek et al. (2017), Scientific Reports, 7, 1399. "
            "https://doi.org/10.1038/s41598-017-01362-7. "
            "Licensed under CC BY 4.0."
        ),
        width=500,
    )

st.markdown(
    """
In this app, empirical runup models are used to estimate the shoreline elevation reached by waves,
either for a **single user-defined scenario** or for a **short Mediterranean forecast period**.

### Pages in this app

**Manual calculator**  
This page is designed for single scenarios. You can enter significant wave height, peak period,
beach slope, and optionally a water-level contribution and a critical elevation threshold.
You can also upload a beach profile to visualize how the modelled runup or total water level
intersects the shore.

It is useful for:
- comparing empirical runup models
- testing sensitivity to waves, slope, and water level
- visualizing possible exceedance of a critical elevation
- teaching how model spread affects coastal water-level estimates

**Mediterranean forecast**  
This page is designed for short-term exploration of forecast conditions at a selected offshore point
in the Mediterranean. The app extracts wave conditions from Copernicus Marine and computes a time-varying
runup or total water level signal across the available empirical models.

Depending on the selected option, total water level can be estimated using:
- a constant user-defined water-level offset
- or a **Copernicus mean-removed sea-level signal**

This page is useful for:
- identifying the most energetic forecast day
- exploring how runup evolves through the forecast window
- checking possible exceedance of a critical threshold using a daily traffic-light summary

### Important note

This app is intended for **scientific exploration, teaching, and preliminary screening only**.  
It is **not** a substitute for site-specific engineering analysis, hazard assessment, or operational coastal-risk decisions.  
Use at your own risk.
"""
)

st.info("Use the sidebar to open the Manual calculator or the Mediterranean forecast page.")