# mapillary_streamlit.py
import streamlit as st
from pathlib import Path
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
import os

st.set_page_config(layout="wide")
st.title("StreetSmart — Cincinnati")

html_path = Path(__file__).parent / "map.html"
USER_REQS_PATH = Path("data/User_Requests.csv")
os.makedirs("data", exist_ok=True)

left, right = st.columns([3, 1])

with right:
    st.header("Report a Pothole")
    st.write("Click a location on the map (approximate) and submit details:")

    # store temporary click location
    lat = st.session_state.get("clicked_lat")
    lon = st.session_state.get("clicked_lon")

    with st.form("pothole_form", clear_on_submit=True):
        name = st.text_input("Your name")
        desc = st.text_area("Description")
        severity = st.selectbox("Severity", ["Low", "Medium", "High"])
        submitted = st.form_submit_button("Submit")

        if submitted:
            if lat and lon:
                req = {
                    "id": datetime.utcnow().isoformat(),
                    "name": name,
                    "description": desc,
                    "lat": lat,
                    "lon": lon,
                    "severity": severity,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                if USER_REQS_PATH.exists():
                    df = pd.read_csv(USER_REQS_PATH)
                    df = pd.concat([df, pd.DataFrame([req])], ignore_index=True)
                else:
                    df = pd.DataFrame([req])
                df.to_csv(USER_REQS_PATH, index=False)
                st.success("Request saved")
            else:
                st.error("Please click on the map to set location first.")

with left:
    if not html_path.exists():
        st.error("map.html not found")
    else:
        html = html_path.read_text(encoding="utf-8")
        components.html(html, height=800, scrolling=True)
