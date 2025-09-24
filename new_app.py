# new_app.py
import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd
import requests
import streamlit.components.v1 as components

# -----------------------
# CONFIG
# -----------------------
st.set_page_config(layout="wide", page_title="StreetSmart — Cincinnati")

CINCINNATI_COORDS = (39.1031182, -84.5120196)
USER_REQS_PATH = os.path.join("data", "User_Requests.csv")
CITY_POTHOLE_CSV = os.path.join("data", "Pothole Data.csv")
MAPILLARY_BBOX = "-84.64,39.045,-84.45,39.17"
MAPILLARY_LIMIT = 400
MAPILLARY_TOKEN = "MLY|24809069168781145|42439e0041a38fda5a362a1bda951fbc"

os.makedirs("data", exist_ok=True)

# -----------------------
# Data loading
# -----------------------


@st.cache_data(ttl=300)
def load_pothole_data():
    if not os.path.exists(CITY_POTHOLE_CSV):
        return []
    try:
        df = pd.read_csv(CITY_POTHOLE_CSV)
        open_reqs = df[df.get("SR_STATUS_FLAG", "").astype(str).str.upper() == "OPEN"]
        potholes = []
        for _, row in open_reqs.iterrows():
            try:
                potholes.append(
                    {
                        "lat": float(row["LATITUDE"]),
                        "lon": float(row["LONGITUDE"]),
                        "sr_number": str(row.get("SR_NUMBER", "")),
                        "status": str(row.get("SR_STATUS", "")),
                        "type": str(row.get("SR_TYPE_DESC", "")),
                        "address": str(row.get("ADDRESS", "")),
                    }
                )
            except:
                continue
        return potholes
    except Exception as e:
        st.warning(f"Could not read pothole CSV: {e}")
        return []


def load_user_requests():
    if not os.path.exists(USER_REQS_PATH):
        return []
    try:
        df = pd.read_csv(USER_REQS_PATH)
        return [
            {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "name": str(row.get("name", "")),
                "description": str(row.get("description", "")),
                "severity": str(row.get("severity", "")),
            }
            for _, row in df.iterrows()
        ]
    except:
        return []


@st.cache_data(ttl=600)
def fetch_mapillary_images(bbox, token, limit=200):
    if not token:
        return []
    url = (
        f"https://graph.mapillary.com/images?access_token={token}"
        f"&fields=id,geometry&bbox={bbox}&limit={limit}"
    )
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json().get("data", [])
    except:
        return []


def save_user_request(req: dict):
    if os.path.exists(USER_REQS_PATH):
        try:
            df_existing = pd.read_csv(USER_REQS_PATH)
            df_new = pd.concat([df_existing, pd.DataFrame([req])], ignore_index=True)
        except:
            df_new = pd.DataFrame([req])
    else:
        df_new = pd.DataFrame([req])
    df_new.to_csv(USER_REQS_PATH, index=False)


# -----------------------
# Session state
# -----------------------
if "selected_lat" not in st.session_state:
    st.session_state.selected_lat = None
    st.session_state.selected_lon = None
if "show_mapillary" not in st.session_state:
    st.session_state.show_mapillary = False
    st.session_state.mapillary_image_id = None

# -----------------------
# Map HTML
# -----------------------


def create_interactive_map(potholes, user_requests, mapillary_images):
    potholes_js = json.dumps(potholes)
    user_requests_js = json.dumps(user_requests)
    mapillary_js = json.dumps(
        [
            {
                "lat": item["geometry"]["coordinates"][1],
                "lon": item["geometry"]["coordinates"][0],
                "id": item["id"],
            }
            for item in mapillary_images
            if "geometry" in item
        ]
    )
    sel_lat = (
        "null"
        if st.session_state.selected_lat is None
        else st.session_state.selected_lat
    )
    sel_lon = (
        "null"
        if st.session_state.selected_lon is None
        else st.session_state.selected_lon
    )

    return f"""
    <div id="map" style="height:700px;width:100%;"></div>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/js/all.min.js"></script>
    <script>
      const potholes = {potholes_js};
      const userRequests = {user_requests_js};
      const mapillaryImages = {mapillary_js};
      const selLat = {sel_lat};
      const selLon = {sel_lon};

      const map = L.map('map').setView([{CINCINNATI_COORDS[0]}, {CINCINNATI_COORDS[1]}], 12);
      const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'© OpenStreetMap'}}).addTo(map);
      const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{attribution:'Esri World Imagery'}});

      const potholeLayer = L.layerGroup().addTo(map);
      const userLayer = L.layerGroup().addTo(map);
      const mapillaryLayer = L.layerGroup().addTo(map);
      const selectedLayer = L.layerGroup().addTo(map);

      L.control.layers({{"OSM":osm,"Satellite":satellite}},{{"Potholes":potholeLayer,"User Requests":userLayer,"Mapillary":mapillaryLayer}}).addTo(map);

      potholes.forEach(p => {{
        L.circleMarker([p.lat,p.lon],{{radius:6,color:'darkred',fillColor:'red',fillOpacity:0.7}})
          .bindPopup("SR #" + p.sr_number + "<br>Status:" + p.status + "<br>Address:" + p.address)
          .addTo(potholeLayer);
      }});

      userRequests.forEach(r => {{
        var icon = L.divIcon({{html:'<i class="fas fa-wrench" style="color:blue"></i>',iconSize:[20,20]}});
        L.marker([r.lat,r.lon],{{icon:icon}})
          .bindPopup(r.name + "<br>" + r.description + "<br>Severity: " + r.severity)
          .addTo(userLayer);
      }});

      mapillaryImages.forEach(img => {{
        var icon = L.divIcon({{html:'<i class="fas fa-camera" style="color:green"></i>',iconSize:[20,20]}});
        L.marker([img.lat,img.lon],{{icon:icon}})
          .bindPopup("Click to view street view")
          .on('click',()=>{{window.parent.postMessage({{type:'mapillary_click',imageId:img.id}},'*');}})
          .addTo(mapillaryLayer);
      }});

      var selectedMarker = null;
      if(selLat !== null && selLon !== null){{
        selectedMarker = L.marker([selLat,selLon],{{icon:L.divIcon({{html:'<i class="fas fa-plus" style="color:green;font-size:20px"></i>',iconSize:[25,25]}})}}).addTo(selectedLayer);
      }}

      map.on('click', e => {{
        if(selectedMarker) selectedLayer.removeLayer(selectedMarker);
        selectedMarker = L.marker([e.latlng.lat,e.latlng.lng],{{icon:L.divIcon({{html:'<i class="fas fa-plus" style="color:green;font-size:20px"></i>',iconSize:[25,25]}})}}).addTo(selectedLayer);
        window.parent.postMessage({{type:'map_click',lat:e.latlng.lat,lng:e.latlng.lng}}, '*');
      }});
    </script>
    """


# -----------------------
# Global JS listener (Streamlit DOM side)
# -----------------------


def handle_js_messages():
    js_code = """
    <script>
    window.addEventListener("message", (event) => {
        if (event.data.type === "map_click") {
            const lat = event.data.lat;
            const lon = event.data.lng;
            fetch("/_stcore/streamlit_javascript_message", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({type: "map_click", lat: lat, lon: lon})
            });
        } else if (event.data.type === "mapillary_click") {
            fetch("/_stcore/streamlit_javascript_message", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({type: "mapillary_click", imageId: event.data.imageId})
            });
        }
    });
    </script>
    """
    components.html(js_code, height=0, width=0)


# -----------------------
# Main app
# -----------------------


def main():
    st.title("StreetSmart — Cincinnati")

    potholes = load_pothole_data()
    user_requests = load_user_requests()
    mapillary_images = fetch_mapillary_images(
        MAPILLARY_BBOX, MAPILLARY_TOKEN, MAPILLARY_LIMIT
    )

    left_col, right_col = st.columns([3, 1])

    # RIGHT: form
    with right_col:
        st.header("Report a Pothole")
        if st.session_state.selected_lat and st.session_state.selected_lon:
            st.success(
                f"Selected: {st.session_state.selected_lat:.6f}, {st.session_state.selected_lon:.6f}"
            )
        else:
            st.info("Click the map to select location.")

        with st.form("request_form", clear_on_submit=False):
            name = st.text_input("Your name", key="name_input")
            description = st.text_area("Description / notes", key="desc_input")
            severity = st.selectbox(
                "Severity", ["Low", "Medium", "High"], key="severity_input"
            )
            submitted = st.form_submit_button("Submit repair request")

            if submitted:
                if not (
                    st.session_state.selected_lat and st.session_state.selected_lon
                ):
                    st.error("Click on the map first.")
                else:
                    req = {
                        "id": datetime.utcnow().isoformat(),
                        "name": name or "anonymous",
                        "description": description or "",
                        "lat": st.session_state.selected_lat,
                        "lon": st.session_state.selected_lon,
                        "severity": severity,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    save_user_request(req)
                    st.success("Repair request submitted!")
                    st.session_state.selected_lat = None
                    st.session_state.selected_lon = None
                    st.session_state["name_input"] = ""
                    st.session_state["desc_input"] = ""
                    st.session_state["severity_input"] = "Low"
                    st.experimental_rerun()

        st.markdown("---")
        st.subheader("Recent user requests")
        if os.path.exists(USER_REQS_PATH):
            try:
                df_preview = (
                    pd.read_csv(USER_REQS_PATH)
                    .sort_values("timestamp", ascending=False)
                    .head(10)
                )
                st.dataframe(df_preview)
            except:
                st.info("No saved requests yet.")
        else:
            st.info("No saved requests yet.")

    # LEFT: map or Mapillary viewer
    with left_col:
        if st.session_state.show_mapillary and st.session_state.mapillary_image_id:
            mapillary_html = f"""
            <div id="mapillary" style="width:100%;height:600px;"></div>
            <link href="https://unpkg.com/mapillary-js@4.1.2/dist/mapillary.css" rel="stylesheet" />
            <script src="https://unpkg.com/mapillary-js@4.1.2/dist/mapillary.js"></script>
            <script>
                var viewer = new Mapillary.Viewer({{
                    accessToken: "{MAPILLARY_TOKEN}",
                    container: "mapillary",
                    imageId: "{st.session_state.mapillary_image_id}"
                }});
            </script>
            """
            components.html(mapillary_html, height=600)
            if st.button("← Back to Map"):
                st.session_state.show_mapillary = False
                st.session_state.mapillary_image_id = None
                st.experimental_rerun()
        else:
            components.html(
                create_interactive_map(potholes, user_requests, mapillary_images),
                height=700,
            )

    # Inject listener once
    handle_js_messages()


# -----------------------
# Run app
# -----------------------
if __name__ == "__main__":
    main()
