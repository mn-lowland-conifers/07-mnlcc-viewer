# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AKSDB Explorer is a web map application for viewing, querying, and eventually validating spatial
prediction products from the Alaska Soil Data Bank project. It displays Google Earth Engine image
assets through a FastAPI backend and a Leaflet frontend: dynamic layer loading, satellite/OSM
basemaps, opacity control, browser geolocation, legends, and click-to-query raster values.

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

Local dev auth: Earth Engine uses the `earthengine authenticate` persistent user token already
set up in this environment (`~/.config/earthengine/credentials`). No service account key needed
for local dev.

Docker (validates the Cloud Run container locally):
```bash
cd backend
docker build -t aksdb-api-test .
docker run -d --name aksdb-api-test-run -p 8081:8080 \
  -e PORT=8080 -e GEE_PROJECT_ID=ee-jeli0026 -e CORS_ORIGINS=http://127.0.0.1:5500 \
  -v "$HOME/.config/earthengine:/root/.config/earthengine:ro" \
  aksdb-api-test
curl http://127.0.0.1:8081/health
```
Mounting `~/.config/earthengine` read-only lets the container authenticate via the same fallback
path local dev uses (see Architecture below), without needing GCP ADC set up locally.

There is no test suite yet (`tests/` is an empty placeholder) and no linter is configured.

Deploy backend to Cloud Run (see Infrastructure section for the one-time setup this depends on):
```bash
gcloud run deploy aksdb-api \
  --source backend \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account=aksdb-api-runner@ee-jeli0026.iam.gserviceaccount.com \
  --set-env-vars="^;^GEE_PROJECT_ID=ee-jeli0026;CORS_ORIGINS=<comma-separated origins>" \
  --project=ee-jeli0026
```
Note the `^;^` prefix on `--set-env-vars`: `CORS_ORIGINS` itself contains commas, which collides
with gcloud's default comma-delimiter for that flag, so the delimiter is remapped to `;`.

`gcloud` is installed at `~/google-cloud-sdk/bin/gcloud` on this machine and is not always on
PATH in non-interactive shells — use the full path if `gcloud` isn't found.

## Architecture

### Backend (`backend/`)

- `app.py` — FastAPI app. Initializes Earth Engine at import time via `_init_earth_engine()`,
  then defines the four routes.
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
Cloud Run to work at all.

### Layer catalog (`backend/layers.json`)

Layer types (`get_layer_image` in `layers.py`):
- `gee_image` — a direct EE image asset. Supports `band` (select a single band, needed for
  multi-band assets), `nodata_value`, `valid_min`, `valid_max`, `value_multiplier`, `value_offset`,
  `self_mask`.
- `threshold_binary` — binarizes another *configured* layer (via `source_layer` + `threshold`,
  compared post-transform, i.e. in the same units as the source layer's public values — e.g.
  percent, not raw 0–200).
- `peat_pf_combo` — derived categorical layer combining a peat binary + a permafrost binary layer.
- `soil_extent_mask` — derived from a metric-filtered `ee.ImageCollection` (mask ∩ probability>0).

Convention: a layer can be temporarily hidden from the app with `"enabled": false` without
deleting its definition — `public_layer_metadata()` filters these out. This is the JSON-native
substitute for "commenting out" a layer (JSON has no comment syntax). Used to retire the AKSDB
v1-2/v1-3 layers when v1-4 layers replaced them (see Recent Work below) — their configs are still
in the file for reference/rollback.

Gotcha specific to this project's categorical rasters: don't use `self_mask` on an argmax/class
layer where `0` is a real class (e.g. Andisols in the soil-order layers) — `.selfMask()` masks out
zero-valued pixels, which is wrong for a real class ID. Use `nodata_value` (exact-value mask) or
`valid_min` (inequality mask) instead, matching whatever the source script's actual nodata
sentinel is (255 for the AKSDB argmax layers, -1 for the gSSURGO dominant-order layer).

### Frontend (`frontend/`)

Static Leaflet app (`index.html`, `app.js`, `style.css`), no build step. `app.js` calls `GET
/layers` on load, registers every returned layer as a Leaflet overlay, and builds legends
(continuous gradient or categorical swatches, per `legend_type`) from the same metadata — the
frontend has no hardcoded layer list.

## Infrastructure / Deployment

**Decision: Google Cloud Run (backend) + Cloudflare Pages (frontend)**, not the EC2/Nginx +
S3/CloudFront plan sketched in `docs/deployment.md`. Rationale: the backend already lives in the
same GCP project as the Earth Engine assets (`ee-jeli0026`), so Cloud Run can use an attached
service account for EE auth via ADC with no downloaded key file to manage; it scales to zero
(near-$0 for this traffic level); and there's no server/Nginx/TLS to maintain. Cloudflare Pages
was chosen for the frontend because the project's landing page is already hosted there — same
dashboard, same DNS, free, automatic HTTPS.

### Current live deployment

- Cloud Run service: `aksdb-api`, region `us-central1`, project `ee-jeli0026`.
- URL: `https://aksdb-api-1062400256329.us-central1.run.app`
- Public/unauthenticated (`--allow-unauthenticated`) — required since the frontend calls it
  without any login, same as local dev.
- Runtime service account: `aksdb-api-runner@ee-jeli0026.iam.gserviceaccount.com`, granted:
  - `roles/earthengine.writer` — **not** `roles/earthengine.viewer`. Viewer is insufficient even
    for read-only tile serving: generating a tile map ID (`img.getMapId()` /
    `earthengine.maps.create`) requires the writer role's permission set. This was discovered via
    a live 403 (`Permission 'earthengine.maps.create' denied`) after initially granting viewer.
  - `roles/serviceusage.serviceUsageConsumer` — required for the service account to make any
    billed API calls against the project at all; without it, `ee.Initialize()` itself fails with
    a `USER_PROJECT_DENIED` 403.
- Container: `backend/Dockerfile` (python:3.11-slim, gunicorn + `uvicorn.workers.UvicornWorker`,
  binds `$PORT` per Cloud Run's contract). `backend/.dockerignore` excludes `.venv/`, `.env`,
  caches.

### Billing

An existing GCP billing account ("My Billing Account", `012C51-7D888A-F3D8EA`) was linked to the
`ee-jeli0026` project to enable Cloud Run/Cloud Build/Artifact Registry (all three require billing
to be enabled on the project, even to stay within their free tiers). **This does not affect Earth
Engine's noncommercial/free registration** — EE's noncommercial licensing is a separate
registration (made at signup) from whether Cloud Billing is enabled on the project; enabling
billing only lets the project use other GCP services, billed independently of EE usage. Expected
Cloud Run cost is ~$0/month at this traffic level (scale-to-zero, default `min-instances=0`, so a
cold start of ~1–3s is expected on the first request after idle — accepted as a fine tradeoff for
a research/demo tool).

### Known issue / TODO

`soil_extent_mask_v2026` reads from `projects/akveg-map/assets/...` — a GCP project the site owner
does not administer. The Cloud Run service account has no access to it, so this one layer 500s in
production (works fine in local dev, which still authenticates via the developer's own EE user
credentials that do have access). Planned fix: replace the source with the developer's own
uploaded `.tif` asset in `ee-jeli0026` once available; not a blocker for the rest of the app.

### Frontend deployment (live)

- Hosted on Cloudflare Pages, git-connected to `alaska-soil-data-bank/aksdb-viewer` on `main`.
  No build command; build output directory is `frontend`.
- Custom domain: `https://maps.aksoildatabank.org` (DNS + SSL managed by Cloudflare, since
  `aksoildatabank.org` is already on the same Cloudflare account as the project's landing page).
- `frontend/config.js`'s `API_BASE` points at the Cloud Run URL above.
- Cloud Run `CORS_ORIGINS` is set to
  `https://maps.aksoildatabank.org,http://127.0.0.1:5500,http://localhost:5500` — the local dev
  origins are kept alongside the production domain so a local frontend can still be pointed at a
  local backend during development.

Full stack, end to end: `maps.aksoildatabank.org` (Cloudflare Pages) → `aksdb-api` (Cloud Run) →
Earth Engine. Verified live with 12/13 layers serving correctly (see Known Issue above for the
one exception).

## Recent Work Log

Session-by-session record of substantive changes, most recent first, kept here because the
"why" behind these choices isn't otherwise recoverable from the code alone.

**Cloud Run deployment (this session):**
- Added `backend/Dockerfile` and `backend/.dockerignore`.
- Fixed `ee.Initialize()` in `app.py` to be ADC-aware (see Architecture note above) — required for
  the container to authenticate as the Cloud Run service account instead of only supporting the
  local `earthengine authenticate` flow.
- Added `google-auth` to `requirements.txt` (previously an untracked transitive dependency).
- Created service account `aksdb-api-runner`, iterated on its IAM roles live against real 403s
  (see Infrastructure section) until `roles/earthengine.writer` +
  `roles/serviceusage.serviceUsageConsumer` proved sufficient.
- Linked existing GCP billing account to `ee-jeli0026`; enabled Cloud Run Admin API, Cloud Build
  API, Artifact Registry API.
- Deployed and verified all endpoints; 12 of 13 layers confirmed serving tiles correctly in
  production (`soil_extent_mask_v2026` excluded — see Known Issue above).

**Layer catalog overhaul (this session):**
- Retired the AKSDB v1-2/v1-3 layers (`pf_prob_aksdb_v2`, `peat_prob_aksdb_v2`,
  `pf_binary_aksdb_v2`, `peat_binary_aksdb_v2`, `peat_pf_combo_aksdb_v2`, `soil_order_aksdb_v3`) by
  setting `"enabled": false` rather than deleting them — introduced the `enabled` flag convention
  itself (`public_layer_metadata()` in `layers.py` now filters on it) as the JSON equivalent of
  commenting the layers out.
- Added AKSDB v1-4 layers: `all_peat_prob_aksdb_v4` / `all_peat_binary_aksdb_v4` (exp055, ≥35%,
  color `c9a96e`), `deep_peat_prob_aksdb_v4` / `deep_peat_binary_aksdb_v4` (exp054, ≥25.5%, color
  `3d2209`) — note exp054/exp055 were initially wired to the wrong all/deep labels and corrected
  mid-session; `pf_prob_aksdb_v4` / `pf_binary_aksdb_v4` (exp070 CatBoost-RFE permafrost, ≥38%,
  color `08306b`); `soil_order_aksdb_v4` (exp074 GBM-RFE dominant soil order argmax, 7-class
  palette, deliberately `nodata_value`-masked rather than `self_mask`ed — see the class-0 gotcha
  above).
- Added `gssurgo_deep_peat_pct` (gSSURGO band `b1`, viridis 0–100%) — required adding `band`
  selection support to `get_layer_image()`'s `gee_image` branch, since no prior layer needed it.
- Added `gssurgo_dominant_order` (gSSURGO dominant soil order, same 7-class palette as
  `soil_order_aksdb_v4`, masked via `valid_min: 0` since its nodata sentinel is `-1`, not `255`).
- Kept active throughout: `pastick_pf_prob`, `pastick_pf_binary`, `lara_peat_2021`,
  `soil_extent_mask_v2026`.
- Updated `README.md`'s "Current Layers" list to match.
