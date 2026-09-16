# AKSDB Explorer Architecture

## Overview

AKSDB Explorer uses a three-part architecture:

```text
Browser
  ↓
Leaflet frontend
  ↓
FastAPI backend
  ↓
Google Earth Engine
```

The frontend never talks directly to Earth Engine. All Earth Engine access is handled by the backend.

## Design Goals

The main goals are:

1. Keep the frontend independent of Earth Engine asset details.
2. Keep all layer definitions centralized in `layers.json`.
3. Support both raw Earth Engine images and derived layers.
4. Make new spatial products easy to add.
5. Preserve the option to replace Earth Engine with COGs or other raster services later.
6. Build toward future validation and observation workflows.

## Frontend

The frontend is a static Leaflet application.

Responsibilities:

- render the map
- switch basemaps
- request available layers
- display Earth Engine tiles
- manage layer visibility
- show legends
- control opacity
- locate the user
- query raster values on click

Current frontend files:

```text
frontend/index.html
frontend/app.js
frontend/style.css
```

The frontend starts by calling:

```text
GET /layers
```

It then registers every layer returned by the backend as a Leaflet overlay.

## Backend

The backend is a FastAPI application.

Responsibilities:

- authenticate with Google Earth Engine
- load layer metadata from `layers.json`
- construct Earth Engine images
- generate tile URLs
- query pixel values
- expose a REST API for the frontend

Current backend files:

```text
backend/app.py
backend/layers.py
backend/layers.json
```

## API

### `GET /health`

Returns simple backend health status.

### `GET /layers`

Returns public metadata for every configured map layer.

Used by the frontend to build layer controls and legends.

### `GET /tiles/{layer_id}`

Returns an XYZ tile URL for a given layer.

The backend constructs the Earth Engine image, applies transformations, applies visualization parameters, and returns the tile URL.

### `GET /value/{layer_id}?lat={lat}&lon={lon}`

Returns the raster value at a clicked coordinate.

Used for map popups.

## Layer Catalog

The layer catalog is stored in:

```text
backend/layers.json
```

Each layer has a unique ID, display name, type, visualization parameters, legend metadata, and optional transformation rules.

Example:

```json
{
  "pf_prob_aksdb_v2": {
    "name": "PF Prob — AKSDB v1-2 RF-RFE",
    "type": "gee_image",
    "asset": "projects/ee-jeli0026/assets/exp002_pf_prob8_statewide_v20260628",
    "scale": 30,
    "unit": "%",
    "nodata_value": 255,
    "value_multiplier": 0.5,
    "vis": {
      "min": 0,
      "max": 100,
      "palette": ["440154", "fde725"]
    }
  }
}
```

## Supported Layer Types

### `gee_image`

A direct Earth Engine image asset.

Supported transformations:

- `nodata_value`
- `valid_min`
- `valid_max`
- `value_multiplier`
- `value_offset`
- `self_mask`

### `threshold_binary`

A binary layer derived from another configured source layer.

Example use:

```text
AKSDB permafrost probability ≥ 31%
```

### `peat_pf_combo`

A derived categorical layer built from a peat binary layer and a permafrost binary layer.

Classes:

```text
1 = peat present, no permafrost
2 = peat present + permafrost
```

### `soil_extent_mask`

A derived layer built from the preliminary AKSDB ImageCollection.

The current implementation uses:

```text
Soil_Mask
Dominant_Soil_Order_Probability > 0
```

## Legends

The frontend supports two legend types.

### Continuous

Used for probability layers.

Requires:

```json
"legend_type": "continuous"
```

and a visualization ramp:

```json
"vis": {
  "min": 0,
  "max": 100,
  "palette": [...]
}
```

### Categorical

Used for soil orders, binaries, combo layers, masks, and reference classes.

Requires:

```json
"legend_type": "categorical",
"classes": [
  {"value": 1, "label": "Present", "color": "1565c0"}
]
```

## Current Local Development Flow

Run backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app:app --reload
```

Run frontend:

```bash
cd frontend
python3 -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500
```

## Future Production Architecture

Planned production structure:

```text
User browser
  ↓
CloudFront / S3 static frontend
  ↓
EC2 FastAPI backend
  ↓
Google Earth Engine
  ↓
Postgres/PostGIS
```

Near-term deployment target:

```text
Frontend: S3 + CloudFront
Backend: EC2 + FastAPI + Uvicorn/Gunicorn + Nginx
Data source: Earth Engine
Future database: PostgreSQL/PostGIS
```

## Future Features

Planned additions:

- observation submission
- expert validation records
- user authentication
- photo upload
- PostGIS storage
- nearby pedon lookup
- downloadable query results
- model version comparison
- uncertainty and MESS layers
- persistent public deployment
