# AKSDB Explorer

AKSDB Explorer is a web map application for viewing, querying, and eventually validating spatial prediction products from the Alaska Soil Data Bank project.

The current prototype displays Google Earth Engine image assets through a FastAPI backend and a Leaflet frontend. It supports dynamic layer loading, satellite and OpenStreetMap basemaps, opacity control, browser geolocation, legends, and click-to-query raster values.

## Current Capabilities

- FastAPI backend
- Leaflet frontend
- Google Earth Engine tile serving
- Dynamic layer catalog from `backend/layers.json`
- Continuous and categorical legends
- OpenStreetMap and satellite basemaps
- Locate-me button with GPS marker and accuracy circle
- Click-to-query raster value popup
- Multiple AKSDB, reference, and derived layers

## Current Layers

The current layer catalog includes:

- AKSDB v1-4 all peat (>20cm) probability
- AKSDB v1-4 all peat (>20cm) binary
- AKSDB v1-4 deep peat (>40cm) probability
- AKSDB v1-4 deep peat (>40cm) binary
- Pastick et al. near-surface permafrost probability
- Pastick binary permafrost layer
- Lara et al. 2021 peat map
- AKSDB v2026 soil-extent mask

The AKSDB v1-2/v1-3 layers (permafrost/peat probability and binary, peat+permafrost combo, soil-order argmax) remain defined in `backend/layers.json` with `"enabled": false` and are hidden from the app rather than deleted.

## Repository Structure

```text
aksdb-viewer/

backend/
  app.py
  layers.py
  layers.json
  tinyapp.py
  .venv/

frontend/
  index.html
  app.js
  style.css

docs/
  architecture.md

README.md
.gitignore
```

## Backend

The backend is a FastAPI application.

Main responsibilities:

- authenticate with Earth Engine
- read layer definitions from `layers.json`
- generate Earth Engine tile URLs
- query pixel values
- expose a stable REST API to the frontend

Run locally:

```bash
cd backend
source .venv/bin/activate
uvicorn app:app --reload
```

Backend endpoints:

```text
GET /
GET /health
GET /layers
GET /tiles/{layer_id}
GET /value/{layer_id}?lat={lat}&lon={lon}
```

## Frontend

The frontend is a static Leaflet application.

Run locally:

```bash
cd frontend
python3 -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500
```

The frontend reads available layers from:

```text
http://127.0.0.1:8000/layers
```

This means new layers can usually be added by editing `backend/layers.json`, without changing frontend code.

## Layer Configuration

Map layers are configured in:

```text
backend/layers.json
```

Layer types currently supported:

```text
gee_image
threshold_binary
peat_pf_combo
soil_extent_mask
```

The backend supports common raster transformations, including:

- nodata masking
- valid min/max masking
- value scaling
- value offset
- self masking
- binary thresholding
- derived peat + permafrost combo layers
- collection-derived soil extent mask layers

## Development Notes

The AKSDB v1-2 probability layers are stored as uint8 values from 0-200, where:

```text
percent probability = raw value / 2
```

The layer configuration uses:

```json
"value_multiplier": 0.5
```

to convert raw values to percent before display and query.

## Planned Next Steps

- Clean up old prototype file `tinyapp.py`
- Add `requirements.txt`
- Add EC2 deployment configuration
- Add Nginx reverse proxy
- Add HTTPS/domain
- Add observation/comment submission
- Add Postgres/PostGIS support
- Add authentication for expert validation
