import streamlit as st

st.set_page_config(
    page_title="Wave Runup and TWL Calculator",
    layout="wide",
)

st.title("Wave Runup and Total Water Level Calculator")

st.markdown(
    """
This application is a scientific and teaching tool for estimating **wave runup** and **total water level (TWL)**
using empirical runup formulations and Mediterranean forecast data.

**Wave runup** is the vertical excursion of the shoreline driven by wave swash above the still water level.
In this app, **total water level** is computed by combining runup with an additional water-level contribution,
either provided directly by the user or derived from Copernicus model output.

### Pages in this app

**Manual calculator**  
Use this page to explore a single scenario by entering:
- significant wave height
- peak wave period
- beach slope
- optional water-level offset
- optional critical elevation threshold
- optional beach profile

This page is useful for:
- rapid sensitivity tests
- comparing empirical runup models
- visualizing model spread on an idealized beach profile

**Mediterranean forecast**  
Use this page to generate a short forecast-based assessment for a selected offshore point in the Mediterranean.
The app extracts forecast wave conditions from Copernicus Marine and computes time-varying runup or TWL across the available empirical models.

This page is useful for:
- screening the coming forecast period
- identifying the most energetic forecast day
- exploring possible threshold exceedance using a daily traffic-light summary

### Important note

This app is intended for **scientific exploration, teaching, and preliminary screening only**.
It is **not** a substitute for site-specific engineering analysis, hazard assessment, or operational decision-making.
Use at your own risk.
"""
)

st.info("Use the sidebar to open the Manual calculator or the Mediterranean forecast page.")