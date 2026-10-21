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

Active (shown in the app):

- Peatland Probability (LGBM) — `prob_lgbm`
- Predicted Peat Depth — `depth`
- Predicted Peat Extent (≥36.2% probability) — `peat_extent_mask`, a toggleable reference overlay
  derived from `prob_lgbm`
- Belowground Carbon Stock (Full Profile) — `carbon_belowground_fullstock` (viridis palette)

Defined but currently disabled (`"enabled": false` in `layers.json` — configs kept for later
reactivation, not deleted):

- Peat Composition — Fibric % / Hemic % / Sapric % / Mineral % — `comp_fibric`, `comp_hemic`,
  `comp_sapric`, `comp_mineral`
- NLCD Open Water — `water_mask`

Every layer's display name has `MNLCCv1-0_16SEP2026` appended (product version tag).

All 7 raw layers are automatically masked to exclude USGS NLCD 2021 open water,
developed/impervious land, and barren/extractive land (strip mines, gravel pits, quarries — e.g.
the Mesabi Iron Range open pits), fully transparent rather than a solid color. This is
unconditional, not a toggle. `peat_extent_mask` and `water_mask` above are separate opt-in
reference overlays for showing predicted extent / water boundaries explicitly.

All layers are also masked (fully transparent) over tribal lands, using the dissolved polygon
asset `projects/ee-jeli0026/assets/tribal-lands-mask-dissolved-23SEP2026`. The polygons are drawn
as a thin dark-grey outline with transparent fill by a silent `tribal_outline` overlay — served
via `GET /outlines`, not listed in `/layers`, so it has no legend entry, layer-control toggle, or
click-query behavior.

All layers are additionally clipped to the prediction domain: data is shown only inside the polygon
asset `projects/ee-jeli0026/assets/mn-lowland-conifer-lta-mask-21OCT2026` and is fully transparent
outside it. Like the tribal mask, this is unconditional (no toggle) and has no outline overlay.

Color ramps for `prob_lgbm` and `depth` match Nic's preferred vis params from his trial GEE
scripts (`probability_viewer.txt`, `depth_viewer.txt`, now in `x-example/`).

The visualization ranges (`vis.min`/`vis.max`) for `prob_lgbm` (0–99.5 %), `depth` (6–456 cm) and
`carbon_belowground_fullstock` (33–253 kgC/m²) were set from the actual min/max of
the visible 30 m pixels — i.e. after every mask (prediction domain, tribal lands, NLCD exclusions,
and the peat-extent `mask_layer` for depth/carbon). Computed 2026-10-21 with `ee.Reducer.minMax()`
over a 50 km grid covering the domain (a single domain-wide `reduceRegion` times out). Recompute if
the assets or masks change.

Carbon was then narrowed to 45–130 kgC/m² (≈ 1st–99th percentile; 99% of visible pixels fall in
that range), so viridis spans its full range instead of only the bottom ~40%. Depth and carbon
legends show "+" on the max label (`clamp_max`).

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
GET /outlines
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
