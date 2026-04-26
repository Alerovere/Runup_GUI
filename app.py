import streamlit as st

st.set_page_config(
    page_title="Wave Runup and TWL Calculator",
    layout="wide",
)

st.title("Wave Runup and Total Water Level Calculator")
st.write(
    "Use the navigation in the sidebar to choose between the manual calculator "
    "and the Mediterranean forecast page."
)

st.info(
    "This is now a multipage app. Each page has its own sidebar controls."
)