# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MNLCC Viewer is a web map application for viewing and querying spatial prediction products from
the Minnesota Lowland Carbon Conifer project. It displays Google Earth Engine image assets
through a FastAPI backend and a Leaflet frontend: dynamic layer loading, satellite/OSM basemaps,
opacity control, browser geolocation, legends, and click-to-query raster values.

This project is a sibling of `askdb-viewer` (Alaska Soil Data Bank) and deliberately mirrors its
architecture. Both projects share the same GCP/Earth Engine project (`ee-jeli0026`), but MNLCC
has its own domain (`maps.mnlowlandconifercarbon.org`, live on Cloudflare Pages) and its own
Cloud Run backend — both deployed and verified working (see `docs/deployment.md`).

This repo also holds `x-example/` (a reference copy of the askdb-viewer pattern this project was
scaffolded from) and `_ancillary/` (this file, plus `claude-chat-16SEP2026.md`, the GEE ingest
handoff doc) — neither is part of the app itself.

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
- `nlcd_water` — standalone categorical layer, USGS NLCD 2021 open-water pixels
  (`landcover.eq(11).selfMask()`), independent of any other configured layer. Shares the
  `_nlcd_landcover()` helper with `threshold_binary`'s `exclude_nlcd_water` option. MNLCC-only,
  not in askdb-viewer.

Two current opt-in reference overlays, both `default_visible: false`, neither masking the raw
layers themselves:
- `peat_extent_mask` (`threshold_binary`): `prob_lgbm` ≥ 36.2% (the 0.362 probability cutoff from
  the trial scripts, in percent units) with `exclude_nlcd_water: true`.
- `water_mask` (`nlcd_water`): black open-water reference layer, matching the "NLCD Open Water"
  toggle in Nic's trial scripts. Added after Nic asked for the water mask as its own independent
  toggle rather than only baked into `peat_extent_mask`.

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

**Live.** Cloud Run (backend) + Cloudflare Pages (frontend), same pattern as askdb-viewer, same
rationale (shared `ee-jeli0026` project, ADC-based EE auth, scale-to-zero). See
`docs/deployment.md` for the full checklist, now mostly checked off.

- Backend: `mnlcc-api` on Cloud Run, region `us-central1`, service account
  `mnlcc-api-runner@ee-jeli0026.iam.gserviceaccount.com` with `roles/earthengine.writer` +
  `roles/serviceusage.serviceUsageConsumer`. URL:
  `https://mnlcc-api-1062400256329.us-central1.run.app`.
- Frontend: Cloudflare Pages project connected to this repo's `main` branch, build output
  directory `frontend`. Custom domain `https://maps.mnlowlandconifercarbon.org` active with SSL
  (CNAME → `07-mnlcc-viewer.pages.dev`, added manually in Cloudflare DNS — same-account zones
  still require this manual step, it isn't automatic).
- `frontend/config.js` `API_BASE` points at the Cloud Run URL above.
- Cloud Run `CORS_ORIGINS` includes `https://maps.mnlowlandconifercarbon.org` plus local dev
  origins.

Known gotcha carried over from askdb-viewer's deployment: the Cloud Run service account needs
`roles/earthengine.writer`, not `roles/earthengine.viewer` — viewer is insufficient even for
read-only tile serving, since generating a tile map ID requires the writer role's permission set.

**New gotcha found here:** an uncaught `ee.ee_exception.EEException` (e.g. a missing/not-yet-
ingested asset) in `/tiles` or `/value` produced a 500 with **no CORS headers**, because
Starlette's `ServerErrorMiddleware` wraps *outside* `CORSMiddleware` — an exception that
propagates past the middleware never gets CORS headers attached. The browser then reports this as
a CORS failure, not a normal failed response, and `fetch()` throws. Since the frontend's
`registerGeeLayer` had no try/catch around that `fetch()`, and `prob_lgbm` (both first in
`layers.json` and, at the time, still mid-ingest) is `default_visible: true`, this took down the
*entire* layer-loading loop — the app showed only basemaps, with zero working overlays, even
though 5 of 7 layers were actually fine. Fixed by catching `EEException` in `app.py` (→ proper
`HTTPException`, which does get CORS headers) and by making the frontend skip default-visible
layers that fail to register instead of crashing on them. Lesson: any endpoint that can raise an
unhandled exception needs it caught somewhere `CORSMiddleware` will still see the response, or
local/CORS testing needs to specifically check headers on the *error* path, not just the happy
path — `curl` status-code checks alone missed this.

## Open Items From the GEE Ingest

See `_ancillary/claude-chat-16SEP2026.md` for the full ingest handoff. As of the live
deployment session (2026-09-16), all 7 assets under `mn_lowland_conifer_v20260916/` finished
`COMPLETED` and are readable by the `mnlcc-api-runner` service account — verified via live
`/tiles/{layer_id}` 200s for every raw layer. Remaining open items from the original handoff:

- `prob_lgbm` units: **confirmed** — Nic's own `probability_viewer.txt` script scales raw × 0.005
  to get a 0-1 probability, which is the same underlying scale as this project's percent
  (raw × 0.5, i.e. probability × 100). `layers.json`'s `value_multiplier: 0.5` / `unit: "%"` is
  correct and consistent with the GEE manifest.
- `depth`'s vis max (350cm) now matches Nic's `DEPTH_MAX` in `depth_viewer.txt`.
  `carbon_belowground_fullstock`'s vis range (0-200 kgC/m²) is still a placeholder guess — no
  trial script covers it yet; verify against real data once assets are queryable.
- Whether asset-level public ACLs (for outside EE projects/users) were ever set is unconfirmed —
  not required for the app itself, since `mnlcc-api-runner` reads assets within the same
  `ee-jeli0026` project regardless of ACLs; only matters if someone outside this project needs
  direct EE read access to the assets.

## Recent Work Log

**Standalone water layer + repo reorg (this session):** Nic asked for the NLCD open-water mask
as its own independent toggle (matching the separate "NLCD Open Water" layer in his trial
scripts), not only bundled into `peat_extent_mask`. Added the `nlcd_water` layer type and a
`water_mask` layer using it. Also reorganized the repo root: `example/` → `x-example/`,
`CLAUDE.md` and `claude-chat-16SEP2026.md` → `_ancillary/`, trial scripts
(`depth_viewer.txt`/`probability_viewer.txt`) copied into `x-example/`.

**Full deploy + CORS bug fix (this session):** Walked through the full deployment checklist live:
created `mnlcc-api-runner` service account + IAM roles, deployed to Cloud Run, connected
Cloudflare Pages to this repo (build output dir `frontend`), attached the custom domain (manual
CNAME step required even same-account), verified CORS end to end. Hit and fixed the CORS/EEException
bug described above — found because the app showed zero overlay layers in the browser even though
curl-testing each endpoint individually looked fine; the bug only manifests when a *default-visible*
layer's backend call throws an uncaught exception, which curl status-code checks alone don't
surface. `gcloud`/`git` network commands needed to run in the user's own terminal (not this
session's sandboxed shell) due to a UMN Workspace reauth policy requiring an interactive prompt.

**`peat_extent_mask` layer + real domain:** Read Nic's trial GEE scripts (`probability_viewer.txt`,
`depth_viewer.txt`) for preferred vis params. Ported their "lava" palette (`000000→ffff99`) to
`prob_lgbm` (max 100%) and `depth` (max raised 300→350cm, matching `DEPTH_MAX` in the script). The
scripts also masked depth/probability to peat-probability ≥0.362 + NLCD open-water exclusion —
asked Nic whether to bake that into the raw layers; he wants raw layers unmasked everywhere, with
the mask as a separate toggle. Added `threshold_binary` layer type (ported from askdb-viewer, plus
a new `exclude_nlcd_water` option) and one `peat_extent_mask` layer using it, `default_visible:
false`. Production domain confirmed: `maps.mnlowlandconifercarbon.org`, already on Cloudflare.

**Initial scaffold:** Backend, frontend, and docs scaffolded from the `askdb-viewer` pattern (via
the `example/` reference copy at the repo root, later renamed `x-example/`).
