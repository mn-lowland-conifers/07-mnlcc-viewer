# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MNLCC Viewer is a web map application for viewing and querying spatial prediction products from
the Minnesota Lowland Carbon Conifer project. It displays Google Earth Engine image assets
through a FastAPI backend and a Leaflet frontend: dynamic layer loading, satellite/OSM basemaps,
opacity control, browser geolocation, legends, and click-to-query raster values.

This project is a sibling of `askdb-viewer` (Alaska Soil Data Bank) and deliberately mirrors its
architecture. Both projects share the same GCP/Earth Engine project (`ee-jeli0026`), but MNLCC
has its own domain (`maps.mnlowlandconifercarbon.org`, already on Cloudflare) and its own Cloud
Run/Cloudflare Pages deployment, not yet live (see `docs/deployment.md`).

Three-part architecture:

```text
Browser → Leaflet frontend (frontend/) → FastAPI backend (backend/) → Google Earth Engine
```

The frontend never talks to Earth Engine directly — all EE access goes through the backend. Layer
definitions are centralized in `backend/layers.json`; new spatial products can usually be added by
editing that file alone, without touching frontend code.

## Commands

Backend (local dev):
```bash
cd backend
source .venv/bin/activate
uvicorn app:app --reload
```
Runs at `http://127.0.0.1:8000`. Endpoints: `GET /health`, `GET /layers`, `GET /tiles/{layer_id}`,
`GET /value/{layer_id}?lat={lat}&lon={lon}`.

Frontend (local dev):
```bash
cd frontend
python3 -m http.server 5500
```
Open `http://127.0.0.1:5500`. `frontend/config.js` sets `API_BASE`, which the frontend reads to
call the backend.

Local dev auth: Earth Engine uses the `earthengine authenticate` persistent user token
(`~/.config/earthengine/credentials`). No service account key needed for local dev.

Docker (validates the Cloud Run container locally):
```bash
cd backend
docker build -t mnlcc-api-test .
docker run -d --name mnlcc-api-test-run -p 8081:8080 \
  -e PORT=8080 -e GEE_PROJECT_ID=ee-jeli0026 -e CORS_ORIGINS=http://127.0.0.1:5500 \
  -v "$HOME/.config/earthengine:/root/.config/earthengine:ro" \
  mnlcc-api-test
curl http://127.0.0.1:8081/health
```

There is no test suite yet and no linter is configured.

## Architecture

### Backend (`backend/`)

- `app.py` — FastAPI app. Initializes Earth Engine at import time via `_init_earth_engine()`,
  then defines the routes.
- `layers.py` — loads `layers.json` once at import time into a module-level `LAYERS` dict;
  `get_layer_image(cfg)` builds the `ee.Image` for a layer per its `type`; `public_layer_metadata()`
  is what `/layers` returns to the frontend (strips internal fields like `asset`, filters out
  disabled layers).
- `config.py` — reads `GEE_PROJECT_ID` and `CORS_ORIGINS` from `.env` (local) or the process
  environment (Cloud Run sets these as service env vars).
- `layers.json` — the layer catalog. Each entry is `layer_id: {config}`. This is the primary file
  to edit when adding/changing a spatial product.

Earth Engine auth (`_init_earth_engine` in `app.py`) tries Application Default Credentials first
(the identity Cloud Run attaches via `--service-account`), and falls back to the
`earthengine authenticate` persistent token if ADC isn't available (local dev). This dual path
matters: `ee.Initialize(project=...)` alone does **not** fall back to ADC on its own — it only
checks the persistent token, which is why the explicit `google.auth.default()` call is needed for
Cloud Run to work at all. (Ported verbatim from askdb-viewer, where this was discovered live.)

### Layer catalog (`backend/layers.json`)

`get_layer_image()` (`backend/layers.py`) implements two layer types:

- `gee_image` — a direct EE image asset. Supports `band` (select a single band), `nodata_value`,
  `valid_min`, `valid_max`, `value_multiplier`, `value_offset`, `self_mask`. Used by the 7 raw
  layers, which are **never masked to a predicted-extent boundary** — each renders everywhere its
  own source asset has valid data. This was an explicit decision (see Recent Work Log): Nic's
  trial GEE scripts (`probability_viewer.txt`, `depth_viewer.txt`) masked depth/probability to a
  peat-probability threshold + NLCD water exclusion, but he wants the raw layers shown
  everywhere, with that masking available as a separate toggle instead (see next).
- `threshold_binary` — binarizes another configured layer via `source_layer` + `threshold`
  (compared post-transform, i.e. same units as the source layer's public values — percent, not
  raw 0-200). Ported from askdb-viewer's pattern. Optional `exclude_nlcd_water: true` additionally
  masks out USGS NLCD 2021 open-water pixels via `_nlcd_water_mask()` — a MNLCC-specific addition,
  not in askdb-viewer's version of this type.

The one current `threshold_binary` layer is `peat_extent_mask`: `prob_lgbm` ≥ 36.2%
(the 0.362 probability cutoff from the trial scripts, in percent units) with
`exclude_nlcd_water: true`. `default_visible: false` — it's an opt-in overlay showing predicted
peat extent as a reference boundary, not a mask baked into the raw layers.

askdb-viewer additionally implements `peat_pf_combo` and `soil_extent_mask` derived layer types.
Neither is ported here since no current MNLCC layer needs them — add if/when one does.

All 7 raw layers are single-band ingested assets under
`projects/ee-jeli0026/assets/mn_lowland_conifer_v20260916/`:

| layer_id | source | nodata | multiplier | unit |
|---|---|---|---|---|
| `prob_lgbm` | uint8 0-200 | 255 | 0.5 | % |
| `comp_fibric` | uint8 0-200 | 255 | 0.5 | % |
| `comp_hemic` | uint8 0-200 | 255 | 0.5 | % |
| `comp_sapric` | uint8 0-200 | 255 | 0.5 | % |
| `comp_mineral` | uint8 0-200 | 255 | 0.5 | % |
| `depth` | uint16, cm | 65535 | 1 | cm |
| `carbon_belowground_fullstock` | uint16, kgC/m² | 65535 | 1 | kgC/m² |

For all seven, **0 is a real value** — never use `self_mask` on these, use `nodata_value` (which
`layers.json` already does for each).

Convention (inherited from askdb-viewer): a layer can be hidden from the app with
`"enabled": false` in `layers.json` without deleting its definition — `public_layer_metadata()`
filters these out.

### Frontend (`frontend/`)

Static Leaflet app (`index.html`, `app.js`, `style.css`), no build step. `app.js` calls `GET
/layers` on load, registers every returned layer as a Leaflet overlay, and builds legends from
the same metadata — the frontend has no hardcoded layer list. Map is centered on Minnesota
(`[46.5, -93.5]`, zoom 6), vs. askdb-viewer's Alaska center.

## Infrastructure / Deployment

**Not yet deployed.** Planned: Cloud Run (backend) + Cloudflare Pages (frontend), same pattern
as askdb-viewer, same rationale (shared `ee-jeli0026` project, ADC-based EE auth, scale-to-zero).
See `docs/deployment.md` for the full checklist — service account name, IAM roles, `gcloud run
deploy` command, and the Cloudflare Pages setup are all sketched there but not yet executed.

Known gotcha to carry over from askdb-viewer's deployment: the Cloud Run service account needs
`roles/earthengine.writer`, not `roles/earthengine.viewer` — viewer is insufficient even for
read-only tile serving, since generating a tile map ID requires the writer role's permission set.

## Open Items From the GEE Ingest

See `claude-chat-16SEP2026.md` at the repo root for the full ingest handoff. As of that
handoff:

- 1 of 7 assets (`comp_fibric`) had a task running; the other 6 were queued to submit.
- `prob_lgbm` units: **confirmed** — Nic's own `probability_viewer.txt` script scales raw × 0.005
  to get a 0-1 probability, which is the same underlying scale as this project's percent
  (raw × 0.5, i.e. probability × 100). `layers.json`'s `value_multiplier: 0.5` / `unit: "%"` is
  correct and consistent with the GEE manifest.
- Asset public ACLs had not yet been set.
- `depth`'s vis max (350cm) now matches Nic's `DEPTH_MAX` in `depth_viewer.txt`.
  `carbon_belowground_fullstock`'s vis range (0-200 kgC/m²) is still a placeholder guess — no
  trial script covers it yet; verify against real data once assets are queryable.

## Recent Work Log

**`peat_extent_mask` layer + real domain (this session):** Read Nic's trial GEE scripts
(`probability_viewer.txt`, `depth_viewer.txt` at repo root) for preferred vis params. Ported their
"lava" palette (`000000→ffff99`) to `prob_lgbm` (max 100%) and `depth` (max raised 300→350cm,
matching `DEPTH_MAX` in the script). The scripts also masked depth/probability to peat-probability
≥0.362 + NLCD open-water exclusion — asked Nic whether to bake that into the raw layers; he wants
raw layers unmasked everywhere, with the mask as a separate toggle. Added `threshold_binary` layer
type (ported from askdb-viewer, plus a new `exclude_nlcd_water` option) and one `peat_extent_mask`
layer using it, `default_visible: false`. Production domain confirmed:
`maps.mnlowlandconifercarbon.org`, already on Cloudflare — see `docs/deployment.md`.

**Initial scaffold:** Backend, frontend, and docs scaffolded from the `askdb-viewer` pattern (via
the `example/` reference copy at the repo root).
