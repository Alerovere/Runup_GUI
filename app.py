import streamlit as st

st.set_page_config(
    page_title="Wave Runup and TWL Calculator",
    layout="wide",
)

st.title("Wave Runup and Total Water Level Calculator")

st.markdown(
    """
This application is a scientific and educational tool for estimating **wave runup**
and **total water level (TWL)** on beaches using published empirical formulations.

Wave runup is the uprush of water above the still water level on a beach or coastal slope.
It is commonly discussed together with **wave setup** and **swash**, which together contribute
to the elevation reached by the shoreline during energetic conditions.
"""
)

st.image(
    "https://media.springernature.com/full/springer-static/image/art%3A10.1038%2Fs41598-017-01362-7/MediaObjects/41598_2017_1362_Fig1_HTML.jpg?as=webp",
    caption=(
        "Conceptual components of coastal water levels. "
        "Figure from Vitousek et al. (2017), Scientific Reports, 7, 1399. "
        "https://doi.org/10.1038/s41598-017-01362-7"
    ),
    use_container_width=True,
)

st.subheader("What this app does")
st.markdown(
    """
The app estimates **wave runup** and **total water level** from simplified coastal inputs.

For each empirical model, the app computes wave runup from wave conditions and beach slope,
then combines it with a user-defined **still water level offset**:

**Total water level = wave runup + tide/storm surge offset**

This app currently includes two pages:

- **Manual calculator**  
  Enter significant wave height, wave period, beach slope, and tide + storm surge directly.

- **Mediterranean forecast**  
  Select a point in the Mediterranean Sea and extract a wave forecast from Copernicus Marine,
  then compute a weekly envelope of runup and total water level across models.
"""
)

st.subheader("What empirical runup models are")
st.markdown(
    """
Empirical runup models are simplified equations derived from field observations,
laboratory data, or statistical fitting. They relate coastal wave runup to a small set
of measurable parameters, typically including:

- **Hs**: significant wave height
- **Tp**: wave period
- **beta**: beach slope

These models are useful because they provide rapid first-order estimates without requiring
a full process-based nearshore hydrodynamic model. However, they are not interchangeable,
and different formulations can give different answers because they were developed for
different beaches, hydrodynamic conditions, and datasets.
"""
)

st.subheader("Important limitations")
st.warning(
    """
This application is intended for **scientific exploration, teaching, and preliminary screening only**.

It is **not** a substitute for site-specific engineering analysis, hazard assessment,
or operational decision-making. Results should be used **at your own risk**.

Empirical runup formulations have calibration limits and may not be valid for all beach types,
wave climates, coastal structures, or extreme-event conditions.
"""
)

st.markdown(
    """
Additional limitations to keep in mind:

- The **forecast page** uses offshore or regional model wave conditions, not local surf-zone observations.
- The value entered as **tide + storm surge** must be consistent with your chosen **vertical datum**.
- Local nearshore processes such as refraction, breaking transformation, reflection, permeability,
  morphology, and coastal structures are not explicitly resolved.
"""
)

st.subheader("Acknowledgements")
st.markdown(
    """
This app uses the Python package **py-wave-runup**, developed to consolidate and implement
published empirical wave runup models for coastal scientists and engineers.

Repository: https://github.com/chrisleaman/py-wave-runup
"""
)

st.subheader("Empirical models represented in this app")
st.markdown(
    """
The runup relationships used here are based on published formulations including:

- Stockdon et al. (2006)
- Holman (1986)
- Nielsen (2009)
- Ruggiero et al. (2001)
- Vousdoukas et al. (2012)
- Atkinson et al. (2017)
- Passarella et al. (2018)
- Senechal et al. (2011)
"""
)

st.subheader("Suggested use")
st.markdown(
    """
This app is most appropriate for:

- classroom demonstrations
- rapid sensitivity tests
- comparisons among empirical runup models
- exploratory screening of possible coastal water-level exceedance
"""
)

st.subheader("References")
st.markdown(
    """
Vitousek, S., Barnard, P. L., Fletcher, C. H., Frazer, N., Erikson, L., & Storlazzi, C. D. (2017).
*Doubling of coastal flooding frequency within decades due to sea-level rise*.
**Scientific Reports, 7**, 1399.
https://doi.org/10.1038/s41598-017-01362-7

Stockdon, H. F., Holman, R. A., Howd, P. A., & Sallenger, A. H. (2006).
*Empirical parameterization of setup, swash, and runup*.
**Coastal Engineering, 53**(7), 573-588.
https://doi.org/10.1016/j.coastaleng.2005.12.005

Holman, R. A. (1986).
*Extreme value statistics for wave run-up on a natural beach*.
**Coastal Engineering, 9**, 527-544.
https://doi.org/10.1016/0378-3839(86)90002-5

Nielsen, P. (2009).
*Coastal and Estuarine Processes*.
World Scientific.

Ruggiero, P., Komar, P. D., McDougal, W. G., Marra, J. J., & Beach, R. A. (2001).
*Wave runup, extreme water levels and the erosion of properties backing beaches*.
**Journal of Coastal Research, 17**, 407-419.

Vousdoukas, M. I., Wziatek, D., & Almeida, L. P. (2012).
*Coastal vulnerability assessment based on video wave run-up observations at a mesotidal, steep-sloped beach*.
**Ocean Dynamics, 62**, 123-137.
https://doi.org/10.1007/s10236-011-0480-x

Atkinson, A. L., Power, H. E., Moura, T., Hammond, T., Callaghan, D. P., & Baldock, T. E. (2017).
*Assessment of runup predictions by empirical models on non-truncated beaches on the south-east Australian coast*.
**Coastal Engineering, 119**, 15-31.
https://doi.org/10.1016/j.coastaleng.2016.10.001

Passarella, M., Goldstein, E. B., De Muro, S., & Coco, G. (2018).
*The use of genetic programming to develop a predictor of swash excursion on sandy beaches*.
**Natural Hazards and Earth System Sciences, 18**, 599-611.
https://doi.org/10.5194/nhess-18-599-2018

Senechal, N., Coco, G., Bryan, K. R., & Holman, R. A. (2011).
*Wave runup during extreme storm conditions*.
**Journal of Geophysical Research, 116**.
https://doi.org/10.1029/2010JC006819
"""
)