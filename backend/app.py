from config import CORS_ORIGINS, GEE_PROJECT_ID

import ee
import google.auth
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from layers import get_layer_config, get_layer_image, public_layer_metadata


def _init_earth_engine():
    """Use the Cloud Run service account (via ADC) when available, e.g. in
    production. Falls back to the `earthengine authenticate` user token for
    local development, where no ADC is configured."""

    scopes = [
        "https://www.googleapis.com/auth/earthengine",
        "https://www.googleapis.com/auth/cloud-platform",
    ]

    try:
        credentials, _ = google.auth.default(scopes=scopes)
        ee.Initialize(credentials, project=GEE_PROJECT_ID)
    except google.auth.exceptions.DefaultCredentialsError:
        ee.Initialize(project=GEE_PROJECT_ID)


_init_earth_engine()

app = FastAPI(title="MNLCC Explorer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "MNLCC Explorer API"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/layers")
def layers():
    return public_layer_metadata()


@app.get("/tiles/{layer_id}")
def tiles(layer_id: str):
    cfg = get_layer_config(layer_id)

    if cfg is None:
        raise HTTPException(status_code=404, detail="Layer not found")

    try:
        img = get_layer_image(cfg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    map_id = img.getMapId(cfg["vis"])

    return {
        "layer_id": layer_id,
        "tile_url": map_id["tile_fetcher"].url_format,
    }


@app.get("/value/{layer_id}")
def value(layer_id: str, lat: float, lon: float):
    cfg = get_layer_config(layer_id)

    if cfg is None:
        raise HTTPException(status_code=404, detail="Layer not found")

    try:
        img = get_layer_image(cfg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pt = ee.Geometry.Point([lon, lat])
    scale = cfg.get("scale", 30)

    result = img.reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=pt,
        scale=scale,
        maxPixels=1e6,
    ).getInfo()

    return {
        "layer_id": layer_id,
        "lat": lat,
        "lon": lon,
        "scale": scale,
        "unit": cfg.get("unit", ""),
        "value": result,
    }
