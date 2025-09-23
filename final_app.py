import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
from branca.element import Template, MacroElement

# Earth Engine import is optional; import on demand
try:
    import ee
except Exception:
    ee = None

# -----------------------
# CONFIG
# -----------------------
st.set_page_config(layout="wide", page_title="StreetSmart — Cincinnati")

CINCINNATI_COORDS = (39.1031182, -84.5120196)  # lat, lon
USER_REQS_PATH = os.path.join("data", "User_Requests.csv")
CITY_POTHOLE_CSV = os.path.join("data", "Pothole Data.csv")  # optional
MAPILLARY_BBOX = "-84.64,39.045,-84.45,39.17"
MAPILLARY_LIMIT = 400

os.makedirs("data", exist_ok=True)

# -----------------------
# EARTH ENGINE helpers
# -----------------------


def try_initialize_ee():
    """Try initialize Earth Engine once; return (ok, message)."""
    global ee
    if ee is None:
        try:
            import ee as _ee

            ee = _ee
        except Exception:
            ee = None
            return False, "earthengine-api not installed"
    try:
        ee.Initialize()
        return True, "Earth Engine initialized (existing credentials)"
    except Exception as e:
        return False, str(e)


@st.cache_data(ttl=600)
def get_ee_mapid_for_image(_ee_image_repr, vis_params):
    """
    Return mapid dict for an EE Image. Leading underscore prevents Streamlit from trying to hash ee.Image.
    """
    if ee is None:
        raise RuntimeError("Earth Engine not available")
    img = ee.Image(_ee_image_repr)
    return img.getMapId(vis_params)


def add_ee_layer(folium_map, ee_object, vis_params, name):
    """Add Earth Engine layer to folium map (uses get_ee_mapid_for_image, which is cached)."""
    try:
        mapid = get_ee_mapid_for_image(ee_object, vis_params)
        folium.raster_layers.TileLayer(
            tiles=mapid["tile_fetcher"].url_format,
            attr="Google Earth Engine",
            name=name,
            overlay=True,
            control=True,
            tile_size=512,
            zoom_offset=-1,
            max_zoom=22,
        ).add_to(folium_map)
    except Exception as e:
        st.warning(f"Could not add EE layer '{name}': {e}")


# -----------------------
# Mapillary caching
# -----------------------
@st.cache_data(ttl=600)
def fetch_mapillary_images(bbox: str, token: str, limit: int = 200):
    """Cached Mapillary Graph API images fetch (id + geometry)."""
    if not token:
        return []
    url = (
        f"https://graph.mapillary.com/images?access_token={token}"
        f"&fields=id,geometry&bbox={bbox}&limit={limit}"
    )
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        j = r.json()
        return j.get("data", [])
    except Exception:
        return []


# -----------------------
# Overlays
# -----------------------
def add_pothole_csv_layer(folium_map, csv_path):
    if not os.path.exists(csv_path):
        return
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        st.warning(f"Could not read pothole CSV: {e}")
        return

    open_reqs = df[df.get("SR_STATUS_FLAG", "").astype(str).str.upper() == "OPEN"]
    fg = folium.FeatureGroup(name="Open Pothole Requests", show=True)
    for _, row in open_reqs.iterrows():
        try:
            lat = float(row["LATITUDE"])
            lon = float(row["LONGITUDE"])
        except Exception:
            continue
        popup_html = (
            f"<b>SR #{row.get('SR_NUMBER', '')}</b><br>"
            f"Status: {row.get('SR_STATUS', '')}<br>"
            f"Type: {row.get('SR_TYPE_DESC', '')}<br>"
            f"Address: {row.get('ADDRESS', '')}"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color="red",
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"SR #{row.get('SR_NUMBER', '')}",
        ).add_to(fg)
    fg.add_to(folium_map)


def add_user_requests_layer(folium_map, csv_path):
    if not os.path.exists(csv_path):
        return
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return
    fg = folium.FeatureGroup(name="User Repair Requests", show=True)
    for _, row in df.iterrows():
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except Exception:
            continue
        popup_html = (
            f"<b>{row.get('name', '')}</b><br/>{row.get('description', '')}<br/>"
            f"Severity: {row.get('severity', '')}"
        )
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=row.get("severity", ""),
            icon=folium.Icon(color="blue", icon="wrench", prefix="fa"),
        ).add_to(fg)
    fg.add_to(folium_map)


def add_mapillary_markers(folium_map, token):
    if not token:
        return
    data = fetch_mapillary_images(MAPILLARY_BBOX, token, MAPILLARY_LIMIT)
    fg = folium.FeatureGroup(name="Mapillary Images", show=False)
    for item in data:
        try:
            coords = item.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            img_id = item.get("id")
            if not img_id:
                continue

            iframe_html = f"""<!doctype html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link
  href="https://unpkg.com/mapillary-js@4.1.2/dist/mapillary.css"
  rel="stylesheet"
/>
<style>html,body{{margin:0;height:100%;}}#mly{{width:100%;height:100%;background:#000}}</style>
</head><body>
<div id="mly"></div>
<script src="https://unpkg.com/mapillary-js@4.1.2/dist/mapillary.js"></script>
<script>
try {{
  var viewer = new mapillary.Viewer({{
    accessToken: "{token}",
    container: "mly",
    imageId: "{img_id}"
  }});
}} catch(e) {{
  document.body.innerHTML = "<div style='color:#fff;padding:8px;'>Mapillary viewer failed: " + e + "</div>"
}}
</script></body></html>"""
            iframe = folium.IFrame(iframe_html, width=360, height=240)
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(iframe, max_width=380),
                icon=folium.Icon(color="green", icon="camera", prefix="fa"),
            ).add_to(fg)
        except Exception:
            continue
    fg.add_to(folium_map)


# -----------------------
# Client-side immediate marker JS (so the user sees the marker immediately)
# -----------------------
def add_click_marker_js(folium_map, marker_icon_url=None):
    """
    Adds a small JS snippet to the folium map that shows a client-side marker immediately when user clicks.
    The server-side persists the click in session_state (via st_folium return).
    """
    map_name = folium_map.get_name()  # e.g., "map_12345..."
    icon_js = ""
    if marker_icon_url:
        icon_js = f"""
    var clickIcon = L.icon({{
      iconUrl: "{marker_icon_url}",
      iconSize: [25, 41],
      iconAnchor: [12, 41]
    }});"""
    else:
        icon_js = "var clickIcon = null;"

    html = f"""
    <script>
    (function() {{
      var map = {map_name};
      var clientMarker = null;
      {icon_js}
      function onMapClick(e) {{
        if (clientMarker) {{
          map.removeLayer(clientMarker);
          clientMarker = null;
        }}
        var opts = clickIcon ? {{icon: clickIcon}} : {{}};
        clientMarker = L.marker(e.latlng, opts).addTo(map);
      }}
      // remove any previous handler to avoid duplicates (defensive)
      map.off('click');
      map.on('click', onMapClick);
    }})();
    </script>
    """
    tpl = Template(html)
    macro = MacroElement()
    macro._template = tpl
    folium_map.get_root().add_child(macro)


# -----------------------
# UI: Sidebar
# -----------------------
st.sidebar.header("Settings & Credentials")
mapillary_token_input = st.sidebar.text_input(
    "Mapillary token (Graph API client-side)", value="", type="password"
)

ee_ok, ee_msg = try_initialize_ee()
st.sidebar.write("Earth Engine:", ee_msg if ee_ok else ee_msg)

uploaded_ee_json = st.sidebar.file_uploader(
    "Upload Earth Engine service account JSON (optional)", type=["json"]
)
if uploaded_ee_json is not None:
    tmp_path = os.path.join("data", "uploaded_ee.json")
    with open(tmp_path, "wb") as f:
        f.write(uploaded_ee_json.getbuffer())
    try:
        # attempt to initialize using the uploaded json
        with open(tmp_path, "r") as f:
            j = json.load(f)
        client_email = j.get("client_email")
        if client_email and ee is not None:
            credentials = ee.ServiceAccountCredentials(client_email, tmp_path)
            ee.Initialize(credentials)
            st.sidebar.success("Earth Engine initialized from uploaded JSON")
            ee_ok = True
        else:
            st.sidebar.error("Uploaded JSON missing client_email or EE not available")
    except Exception as e:
        st.sidebar.error(f"EE init failed: {e}")
        ee_ok = False

# -----------------------
# Layout: left=map, right=form
# -----------------------
left, right = st.columns([3, 1])

with right:
    st.header("Report a Pothole")
    st.write(
        "Click the map (left) to choose a location; you'll immediately see a marker (client-side). Then submit the form."
    )

    clicked_lat = st.session_state.get("clicked_lat")
    clicked_lon = st.session_state.get("clicked_lon")
    if clicked_lat and clicked_lon:
        st.success(f"Selected: {clicked_lat:.6f}, {clicked_lon:.6f}")
    else:
        st.info("No location selected yet.")

    with st.form("request_form", clear_on_submit=False):
        name = st.text_input("Your name")
        description = st.text_area("Description / notes")
        severity = st.selectbox("Severity", ["Low", "Medium", "High"])
        submitted = st.form_submit_button("Submit repair request")

        if submitted:
            if not (
                st.session_state.get("clicked_lat")
                and st.session_state.get("clicked_lon")
            ):
                st.error(
                    "Please click on the map to set the location before submitting."
                )
            else:
                req = {
                    "id": datetime.utcnow().isoformat(),
                    "name": name or "anonymous",
                    "description": description or "",
                    "lat": float(st.session_state["clicked_lat"]),
                    "lon": float(st.session_state["clicked_lon"]),
                    "severity": severity,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                if os.path.exists(USER_REQS_PATH):
                    try:
                        df_existing = pd.read_csv(USER_REQS_PATH)
                        df_new = pd.concat(
                            [df_existing, pd.DataFrame([req])], ignore_index=True
                        )
                    except Exception:
                        df_new = pd.DataFrame([req])
                else:
                    df_new = pd.DataFrame([req])
                df_new.to_csv(USER_REQS_PATH, index=False)
                st.success("Repair request submitted and saved")

    st.markdown("---")
    st.write("Recent user requests:")
    if os.path.exists(USER_REQS_PATH):
        try:
            df_preview = (
                pd.read_csv(USER_REQS_PATH)
                .sort_values("timestamp", ascending=False)
                .head(10)
            )
            st.dataframe(df_preview)
        except Exception:
            st.info("No saved requests yet.")
    else:
        st.info("No saved requests yet.")

with left:
    st.header("StreetSmart — Cincinnati")

    # ensure session defaults
    if "map_center" not in st.session_state:
        st.session_state["map_center"] = CINCINNATI_COORDS
    if "map_zoom" not in st.session_state:
        st.session_state["map_zoom"] = 12

    # Build folium map ONCE (we'll call st_folium only once)
    m = folium.Map(
        location=st.session_state.get("map_center", CINCINNATI_COORDS),
        zoom_start=st.session_state.get("map_zoom", 12),
        control_scale=True,
        tiles=None,
    )

    # Base layers
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    # folium.TileLayer("CartoDB positron", name="Light").add_to(m)
    # folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
    # folium.TileLayer(
    #     tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    #     attr="Google Satellite",
    #     name="Google Satellite",
    # ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Esri Satellite",
    ).add_to(m)

    # Earth Engine layers (cached mapid). Only add if ee initialized
    # ee_ok2, ee_msg2 = try_initialize_ee()
    # if ee_ok2:
    #     try:
    #         point = ee.Geometry.Point([CINCINNATI_COORDS[1], CINCINNATI_COORDS[0]])
    #         region = point.buffer(20000).bounds()
    #
    #         s2 = (
    #             ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    #             .filterBounds(region)
    #             .filterDate("2025-01-01", "2025-12-31")
    #             .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
    #         )
    #         s2_median = s2.median().clip(region)
    #         s2_vis = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.2}
    #         add_ee_layer(m, s2_median, s2_vis, "Sentinel-2 (2025 median)")
    #
    #         naip = (
    #             ee.ImageCollection("USDA/NAIP/DOQQ")
    #             .filterBounds(region)
    #             .filterDate("2020-01-01", "2023-12-31")
    #         )
    #         naip_mosaic = naip.mosaic().clip(region)
    #         naip_vis = {"bands": ["R", "G", "B"], "min": 0, "max": 255}
    #         add_ee_layer(m, naip_mosaic, naip_vis, "NAIP (2020-2023 mosaic)")
    #     except Exception as e:
    #         st.warning(f"Could not add Earth Engine layers: {e}")
    # else:
    #     st.info(
    #         "Earth Engine not initialized — upload service JSON in sidebar to enable NAIP/Sentinel layers."
    #     )

    # Add CSV overlays
    add_pothole_csv_layer(m, CITY_POTHOLE_CSV)
    add_user_requests_layer(m, USER_REQS_PATH)

    # Add Mapillary markers (cached)
    if mapillary_token_input:
        add_mapillary_markers(m, mapillary_token_input)
    else:
        st.info("No Mapillary token provided — Mapillary markers disabled.")

    # If server-side clicked location exists, draw a persistent marker (will appear after rerun)
    if st.session_state.get("clicked_lat") and st.session_state.get("clicked_lon"):
        folium.Marker(
            [
                float(st.session_state["clicked_lat"]),
                float(st.session_state["clicked_lon"]),
            ],
            tooltip="Selected location",
            icon=folium.Icon(color="green", icon="plus", prefix="fa"),
        ).add_to(m)

    # Add layer control
    folium.LayerControl().add_to(m)

    # Add client-side immediate marker JS (so user sees a marker right away on click)
    add_click_marker_js(m)

    # Render map (only once). st_folium returns last_clicked, center, zoom, etc.
    st_data = st_folium(m, width=900, height=700)

    # Handle st_folium output: update session_state only when values change (to avoid rerun loops)
    if st_data:
        # last_clicked -> persist into session_state (update only if changed)
        last_clicked = st_data.get("last_clicked")
        if last_clicked:
            lat = last_clicked.get("lat")
            lng = last_clicked.get("lng")
            if lat is not None and lng is not None:
                if (
                    st.session_state.get("clicked_lat") != lat
                    or st.session_state.get("clicked_lon") != lng
                ):
                    st.session_state["clicked_lat"] = lat
                    st.session_state["clicked_lon"] = lng

        # preserve center & zoom if provided
        center = st_data.get("center")
        zoom = st_data.get("zoom")
        if center and isinstance(center, dict):
            new_center = (center.get("lat"), center.get("lng"))
            if st.session_state.get("map_center") != new_center:
                st.session_state["map_center"] = new_center
        if isinstance(zoom, (int, float)):
            if st.session_state.get("map_zoom") != int(zoom):
                st.session_state["map_zoom"] = int(zoom)

# End of file

