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

col1, col2, col3 = st.columns([0.2, 4.6, 0.2])
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
beach slope, and optionally a water-level contribution, a critical elevation threshold, and a beach profile.
The app compares several empirical runup models, highlights threshold exceedance, and can project the results onto a shoreline profile.

**Mediterranean forecast**  
This page is designed for short-term exploration of forecast conditions at a selected offshore point in the Mediterranean.
The app extracts wave conditions from Copernicus Marine and computes a time-varying runup or total water level signal across the available empirical models.
Depending on the selected option, total water level can be estimated using either a constant user-defined offset
or a **Copernicus mean-removed sea-level signal** derived from modelled sea surface height.

**Multi-source forecast**  
This page compares independent wave forecasts at a single point from Copernicus Marine, NOAA WaveWatch III, and Open-Meteo Marine,
merging them into one table so forecast agreement between sources can be checked before relying on any single model.

### Important note

This app is intended for **scientific exploration, teaching, and preliminary screening only**.  
It is **not** a substitute for site-specific engineering analysis, hazard assessment, or operational coastal-risk decisions.  
Use at your own risk.
"""
)

st.subheader("Acknowledgements")

st.markdown(
    """
This application builds on the Python package **py-wave-runup**, which provides implementations of empirical wave runup models for coastal scientists and engineers.
"""
)

st.caption("py-wave-runup repository: https://github.com/chrisleaman/py-wave-runup")

st.markdown(
    """
The Mediterranean forecast page uses two Copernicus Marine products:

- **Mediterranean Sea Waves Analysis and Forecast**  
  Product ID: `MEDSEA_ANALYSISFORECAST_WAV_006_017`  
  DOI: `10.48670/mds-00373`

- **Mediterranean Sea Physics Analysis and Forecast**  
  Product ID: `MEDSEA_ANALYSISFORECAST_PHY_006_013`  
  DOI: `10.48670/mds-00359`
"""
)

st.caption(
    "Source: European Union, Copernicus Marine Service Information or Data, implemented by Mercator Ocean International."
)

st.markdown(
    """
Generated using **E.U. Copernicus Marine Service Information**.
"""
)

st.markdown(
    """
The Multi-source forecast page additionally cross-checks the Copernicus Mediterranean wave forecast against:

- **NOAA WaveWatch III**, global wave model operated by NOAA/NCEP, accessed via the PacIOOS ERDDAP server
- **Open-Meteo Marine API**, a free aggregator of several global wave models (NOAA GFS-Wave, DWD ICON-Wave, ECMWF WAM)
"""
)

st.subheader("Key references")

st.markdown(
    """
Vitousek, S., Barnard, P. L., Fletcher, C. H., Frazer, N., Erikson, L., & Storlazzi, C. D. (2017).  
*Doubling of coastal flooding frequency within decades due to sea-level rise.*  
**Scientific Reports, 7**, 1399.  
https://doi.org/10.1038/s41598-017-01362-7

Stockdon, H. F., Holman, R. A., Howd, P. A., & Sallenger, A. H. (2006).  
*Empirical parameterization of setup, swash, and runup.*  
**Coastal Engineering, 53**(7), 573-588.  
https://doi.org/10.1016/j.coastaleng.2005.12.005

Holman, R. A. (1986).  
*Extreme value statistics for wave run-up on a natural beach.*  
**Coastal Engineering, 9**, 527-544.  
https://doi.org/10.1016/0378-3839(86)90002-5

Nielsen, P. (2009).  
*Coastal and Estuarine Processes.*  
World Scientific.

Ruggiero, P., Komar, P. D., McDougal, W. G., Marra, J. J., & Beach, R. A. (2001).  
*Wave runup, extreme water levels and the erosion of properties backing beaches.*  
**Journal of Coastal Research, 17**, 407-419.

Vousdoukas, M. I., Wziatek, D., & Almeida, L. P. (2012).  
*Coastal vulnerability assessment based on video wave run-up observations at a mesotidal, steep-sloped beach.*  
**Ocean Dynamics, 62**, 123-137.  
https://doi.org/10.1007/s10236-011-0480-x

Atkinson, A. L., Power, H. E., Moura, T., Hammond, T., Callaghan, D. P., & Baldock, T. E. (2017).  
*Assessment of runup predictions by empirical models on non-truncated beaches on the south-east Australian coast.*  
**Coastal Engineering, 119**, 15-31.  
https://doi.org/10.1016/j.coastaleng.2016.10.001

Passarella, M., Goldstein, E. B., De Muro, S., & Coco, G. (2018).  
*The use of genetic programming to develop a predictor of swash excursion on sandy beaches.*  
**Natural Hazards and Earth System Sciences, 18**, 599-611.  
https://doi.org/10.5194/nhess-18-599-2018

Senechal, N., Coco, G., Bryan, K. R., & Holman, R. A. (2011).  
*Wave runup during extreme storm conditions.*  
**Journal of Geophysical Research, 116**.  
https://doi.org/10.1029/2010JC006819
"""
)

st.info("Use the sidebar to open the Manual calculator, Mediterranean forecast, Wave Explorer, or Multi-source forecast page.")