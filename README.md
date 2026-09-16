# MNLCC Viewer

MNLCC Viewer is a web map application for viewing and querying spatial prediction products from
the Minnesota Lowland Carbon Conifer (MNLCC) project.

It displays Google Earth Engine image assets through a FastAPI backend and a Leaflet frontend.
It supports dynamic layer loading, satellite and OpenStreetMap basemaps, opacity control, browser
geolocation, legends, and click-to-query raster values. Architecture mirrors the sibling
`askdb-viewer` project (Alaska Soil Data Bank).

**Live:** [maps.mnlowlandconifercarbon.org](https://maps.mnlowlandconifercarbon.org)
(Cloudflare Pages, backed by a FastAPI service on Cloud Run).

## Current Capabilities

- FastAPI backend
- Leaflet frontend
- Google Earth Engine tile serving
- Dynamic layer catalog from `backend/layers.json`
- Continuous and categorical legends
- OpenStreetMap and satellite basemaps
- Locate-me button with GPS marker and accuracy circle
- Click-to-query raster value popup

## Current Layers

Source data: 7 Cloud Optimized GeoTIFFs from `gs://mn-lowland-conifer-covars`, ingested as GEE
assets under `projects/ee-jeli0026/assets/mn_lowland_conifer_v20260916/` (all `COMPLETED` — see
`_ancillary/claude-chat-16SEP2026.md` for the ingest process and status history).

- Peatland Probability (LGBM) — `prob_lgbm`
- Peat Composition — Fibric % — `comp_fibric`
- Peat Composition — Hemic % — `comp_hemic`
- Peat Composition — Sapric % — `comp_sapric`
- Peat Composition — Mineral % — `comp_mineral`
- Predicted Peat Depth — `depth`
- Belowground Carbon Stock (Full Profile) — `carbon_belowground_fullstock` (viridis palette)
- Predicted Peat Extent (≥36.2% probability) — `peat_extent_mask`, a toggleable reference overlay
  derived from `prob_lgbm`
- NLCD Open Water — `water_mask`, a standalone toggleable reference overlay

Every layer's display name has `MNLCCv1-0_16SEP2026` appended (product version tag).

All 7 raw layers are automatically masked to exclude USGS NLCD 2021 open water,
developed/impervious land, and barren/extractive land (strip mines, gravel pits, quarries — e.g.
the Mesabi Iron Range open pits), fully transparent rather than a solid color. This is
unconditional, not a toggle. `peat_extent_mask` and `water_mask` above are separate opt-in
reference overlays for showing predicted extent / water boundaries explicitly.

Color ramps for `prob_lgbm` and `depth` match Nic's preferred vis params from his trial GEE
scripts (`probability_viewer.txt`, `depth_viewer.txt`, now in `x-example/`).

**Note:** the visualization range (`vis.max`) for `carbon_belowground_fullstock` in
`backend/layers.json` is a placeholder estimate (200 kgC/m²) — tune it against actual data ranges
(e.g. via `reduceRegion` with `ee.Reducer.minMax()` in the GEE Code Editor).

## Repository Structure

```text
07-mnlcc-viewer/
backend/
  app.py
  layers.py
  layers.json
  config.py
  requirements.txt
  Dockerfile
  .dockerignore

frontend/
  index.html
  app.js
  style.css
  config.js

docs/
  architecture.md
  deployment.md

_ancillary/
  CLAUDE.md
  claude-chat-16SEP2026.md

x-example/            # askdb-viewer reference copy (not part of this app)

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

Open `http://127.0.0.1:5500`.

The frontend reads available layers from `http://127.0.0.1:8000/layers`. New layers can usually
be added by editing `backend/layers.json`, without changing frontend code.

## Layer Configuration

Map layers are configured in `backend/layers.json`. Three layer types are supported: `gee_image`
(a direct Earth Engine image asset — automatically masked to exclude NLCD open water,
developed/impervious land, and barren/extractive land, plus nodata masking, valid min/max
masking, value scaling/offset, and self-masking), `threshold_binary` (binarizes another
configured layer), and `nlcd_water` (a standalone open-water reference layer, unaffected by the
auto-masking). See `docs/architecture.md` for details.

## Deployment

Live at `maps.mnlowlandconifercarbon.org` via Cloud Run (backend) + Cloudflare Pages (frontend).
See `docs/deployment.md` for the full setup and checklist.

## Planned Next Steps

- Tune `carbon_belowground_fullstock` vis range against real data
- Add observation/comment submission
- Add Postgres/PostGIS support
- Add authentication for expert validation
