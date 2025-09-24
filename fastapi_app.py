import os
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_FILE = os.path.join(BASE_DIR, "app.html")
USER_REQS_PATH = os.path.join(DATA_DIR, "User_Requests.csv")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

app = FastAPI()

# Serve static files (images, css, js)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Serve data folder so CSVs can be fetched
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")


@app.get("/")
async def index():
    """Serve frontend"""
    return FileResponse(INDEX_FILE)


# ----------------------------
# API MODELS
# ----------------------------
class UserRequest(BaseModel):
    id: str
    name: str
    description: str
    severity: str
    lat: float
    lon: float
    timestamp: str


class UpvoteRequest(BaseModel):
    id: str


# ----------------------------
# API ENDPOINTS
# ----------------------------
@app.post("/api/requests")
async def add_request(req: UserRequest):
    """Append new request to CSV"""
    try:
        if os.path.exists(USER_REQS_PATH):
            df = pd.read_csv(USER_REQS_PATH)
        else:
            df = pd.DataFrame(
                columns=[
                    "id",
                    "name",
                    "description",
                    "severity",
                    "lat",
                    "lon",
                    "timestamp",
                    "rating",
                ]
            )

        new_row = {
            "id": req.id,
            "name": req.name,
            "description": req.description,
            "severity": req.severity,
            "lat": req.lat,
            "lon": req.lon,
            "timestamp": req.timestamp,
            "rating": 0,
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(USER_REQS_PATH, index=False)

        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/upvote")
async def upvote_request(upvote: UpvoteRequest):
    """Increment rating of a request by ID"""
    try:
        if not os.path.exists(USER_REQS_PATH):
            return JSONResponse(
                {"status": "error", "message": "No requests file"}, status_code=404
            )

        df = pd.read_csv(USER_REQS_PATH)
        if "rating" not in df.columns:
            df["rating"] = 0

        if upvote.id not in df["id"].astype(str).values:
            return JSONResponse(
                {"status": "error", "message": "Request ID not found"}, status_code=404
            )

        df.loc[df["id"].astype(str) == upvote.id, "rating"] += 1
        df.to_csv(USER_REQS_PATH, index=False)

        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
