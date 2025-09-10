"""
Streamlit app that connects to Google Earth Engine (GEE) and shows a map focused on Cincinnati.
Now includes a switch between satellite imagery, the standard OpenStreetMap view, and NAIP data.
"""

import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import json
import tempfile
import os
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide", page_title="Cincinnati GEE Map")

# --- Helper functions -------------------------------------------------

CINCINNATI_COORDS = (39.1031182, -84.5120196)  # (lat, lon)


def try_initialize_ee():
    try:
        ee.Initialize()
        return True, "Initialized using existing credentials."
    except Exception as e:
        print(e)
        return False, str(e)


def initialize_with_service_account(json_path):
    try:
        with open(json_path, "r") as f:
            j = json.load(f)
        client_email = j.get("client_email")
        if not client_email:
            return False, "Service JSON missing client_email"
        credentials = ee.ServiceAccountCredentials(client_email, json_path)
        ee.Initialize(credentials)
        return True, "Initialized Earth Engine with uploaded service account."
    except Exception as e:
        return False, str(e)


def add_ee_layer(folium_map, ee_object, vis_params, name):
    try:
        ee_image = ee.Image(ee_object)
        map_id_dict = ee_image.getMapId(vis_params)

        folium.raster_layers.TileLayer(
            tiles=map_id_dict["tile_fetcher"].url_format,
            attr="Google Earth Engine",
            name=name,
            overlay=True,
            control=True,
            tile_size=512,  # higher tile size
            zoom_offset=-1,
            max_zoom=22,
        ).add_to(folium_map)

    except Exception as e:
        st.error(f"Failed to add EE layer: {e}")


# Try to initialize with existing credentials right away
initialized, msg = try_initialize_ee()

# --- Main layout: map on the left, controls on the right ----------------
left, right = st.columns([3, 1])

with right:
    st.header("Pothole Repair Requests")
    with st.form("request_form", clear_on_submit=True):
        name = st.text_input("Reporter name")
        description = st.text_area("Description / notes")
        lat = st.number_input("Latitude", value=CINCINNATI_COORDS[0], format="%.6f")
        lon = st.number_input("Longitude", value=CINCINNATI_COORDS[1], format="%.6f")
        severity = st.selectbox("Severity", ["Low", "Medium", "High"])
        submitted = st.form_submit_button("Submit repair request")

        if submitted:
            req = {
                "id": datetime.utcnow().isoformat(),
                "name": name,
                "description": description,
                "lat": float(lat),
                "lon": float(lon),
                "severity": severity,
                "timestamp": datetime.utcnow().isoformat(),
            }
            if "pothole_requests" not in st.session_state:
                st.session_state.pothole_requests = []
            st.session_state.pothole_requests.append(req)
            df = pd.DataFrame(st.session_state.pothole_requests)
            save_path = os.path.join(tempfile.gettempdir(), "pothole_requests.csv")
            df.to_csv(save_path, index=False)
            st.success("Repair request submitted and saved locally.")

    st.markdown("---")
    st.write("Saved requests: ")
    if "pothole_requests" in st.session_state and st.session_state.pothole_requests:
        df_preview = pd.DataFrame(st.session_state.pothole_requests).drop(
            columns=["description"], errors="ignore"
        )
        st.dataframe(df_preview)
    else:
        st.info("No repair requests yet.")

    st.markdown("---")
    if st.button("Run Pothole Detection (placeholder)"):
        st.info(
            "Pothole detection is not yet implemented. Future step: run ML model on imagery tiles and add markers."
        )

with left:
    st.header("Cincinnati — Earth Engine Map View")

    # Create base folium map centered on Cincinnati
    m = folium.Map(
        location=[CINCINNATI_COORDS[0], CINCINNATI_COORDS[1]],
        zoom_start=12,
        control_scale=True,
        tiles=None,
    )

    # Add base layers (standard + satellite)
    folium.TileLayer("OpenStreetMap", name="Standard View").add_to(m)
    folium.TileLayer("CartoDB positron", name="Light View").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Dark View").add_to(m)
    folium.TileLayer(
        tiles="https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.png",
        attr="Map tiles by Stamen Design, CC BY 3.0 — Map data © OpenStreetMap contributors",
        name="Terrain View",
        overlay=False,
        control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Satellite View",
        overlay=False,
        control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri & Sources: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        name="Esri Satellite",
    ).add_to(m)

    if initialized:
        try:
            point = ee.Geometry.Point([CINCINNATI_COORDS[1], CINCINNATI_COORDS[0]])
            region = point.buffer(20000).bounds()

            # Sentinel-2
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(region)
                .filterDate("2025-01-01", "2025-12-31")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
            )
            median = collection.median().clip(region)
            vis_params = {
                "bands": ["B4", "B3", "B2"],
                "min": 0,
                "max": 3000,
                "gamma": 1.2,
            }
            add_ee_layer(m, median, vis_params, "Sentinel-2 (median 2025)")

            # NAIP (highest res, ~1m)
            naip = (
                ee.ImageCollection("USDA/NAIP/DOQQ")
                .filterBounds(region)
                .filterDate("2020-01-01", "2023-11-17")
            )
            naip_mosaic = naip.mosaic().clip(region)
            naip_vis = {"bands": ["R", "G", "B"], "min": 0, "max": 255}
            add_ee_layer(m, naip_mosaic, naip_vis, "NAIP 2020 (1m)")

        except Exception as e:
            st.warning(f"Could not load Earth Engine layer: {e}")
            st.info(
                "If Earth Engine fails, ensure credentials are valid and that the account has access to GEE."
            )
    else:
        st.info(
            "Earth Engine not initialized. Upload credentials or authenticate from the sidebar to load imagery layers."
        )

    if "pothole_requests" in st.session_state:
        for req in st.session_state.pothole_requests:
            try:
                folium.Marker(
                    location=[req["lat"], req["lon"]],
                    popup=folium.Popup(
                        f"<b>{req.get('name', '')}</b><br/>{req.get('description', '')}<br/>Severity: {req.get('severity', '')}",
                        max_width=300,
                    ),
                    tooltip=req.get("severity", "Request"),
                ).add_to(m)
            except Exception:
                continue

    folium.LayerControl().add_to(m)
    st_data = st_folium(m, width=900, height=700)

st.markdown("---")
st.caption(
    "Notes: This is a starting template. Next steps: (1) integrate a pothole detection ML model that runs on imagery tiles or street-level photos; "
    "(2) validate detections with user confirmations; (3) move user submissions to a secure database; (4) add user accounts and edit history."
)
