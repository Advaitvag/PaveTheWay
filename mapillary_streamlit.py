# mapillary_streamlit.py
import streamlit as st
from pathlib import Path
import streamlit.components.v1 as components

st.set_page_config(layout="wide")
st.title("Mapillary — Cincinnati Street Images")

html_path = Path(__file__).parent / "map.html"
if not html_path.exists():
    st.error("map.html not found. Put map.html in the same directory as this script.")
else:
    html = html_path.read_text(encoding="utf-8")
    # embed the HTML directly (the HTML contains the Mapillary token)
    components.html(html, height=800, scrolling=True)
