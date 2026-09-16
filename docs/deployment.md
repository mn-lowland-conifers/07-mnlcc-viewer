# MNLCC Viewer Deployment Notes

## Target Production Architecture

Mirrors the askdb-viewer deployment (see that project's `CLAUDE.md` for the full rationale):
Cloud Run for the backend, Cloudflare Pages for the frontend, since both projects share the
same GCP/Earth Engine project (`ee-jeli0026`) and Cloud Run can use an attached service account
for EE auth via ADC with no downloaded key file to manage.

```text
User browser
  ↓
Cloudflare Pages (frontend)
  ↓
Cloud Run (backend)
  ↓
Google Earth Engine
```

**Status: fully live.** Production domain: `https://maps.mnlowlandconifercarbon.org`, on
Cloudflare (Nic's existing zone). All 7 GEE assets finished ingesting and are serving correctly.

## Frontend

Static files, no build step:

```text
frontend/index.html
frontend/app.js
frontend/style.css
frontend/config.js
```

`frontend/config.js` sets `API_BASE`, currently pointed at the live backend:

```javascript
window.MNLCC_CONFIG = {
  API_BASE: "https://mnlcc-api-1062400256329.us-central1.run.app"
};
```

For local dev, temporarily swap that to `http://127.0.0.1:8000` and run the backend locally.

Custom domain: **`maps.mnlowlandconifercarbon.org`** — live via a Cloudflare Pages project
connected to this repo (`mn-lowland-conifers/07-mnlcc-viewer`, branch `main`, build output
directory `frontend`). The custom domain required one manual step even though the zone is on
the same Cloudflare account: Pages' "Complete DNS setup" flow gives a CNAME
(`maps` → `07-mnlcc-viewer.pages.dev`) that has to be added by hand under that zone's DNS →
Records (proxied/orange-cloud). It does not auto-create itself just because the zone is on the
same account. Once added, the domain went to `Active`/SSL-enabled within a minute or two.

## Backend

Production entry point: `backend/app.py`, served via `backend/Dockerfile`
(gunicorn + `uvicorn.workers.UvicornWorker`, binds `$PORT` per Cloud Run's contract).

Deploy:

```bash
gcloud run deploy mnlcc-api \
  --source backend \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account=mnlcc-api-runner@ee-jeli0026.iam.gserviceaccount.com \
  --set-env-vars="^;^GEE_PROJECT_ID=ee-jeli0026;CORS_ORIGINS=https://maps.mnlowlandconifercarbon.org,http://127.0.0.1:5500,http://localhost:5500" \
  --project=ee-jeli0026
```

The `^;^` prefix on `--set-env-vars` remaps gcloud's list delimiter to `;`, since
`CORS_ORIGINS` itself contains commas.

**Done:** `mnlcc-api-runner@ee-jeli0026.iam.gserviceaccount.com` created with
`roles/earthengine.writer` + `roles/serviceusage.serviceUsageConsumer` (not `viewer` — tile map
ID generation needs the writer role's permission set; confirmed the hard way on askdb-viewer).
Required APIs (Cloud Run Admin, Cloud Build, Artifact Registry, IAM) were already enabled on
`ee-jeli0026` from the askdb-viewer setup.

**Live:** deployed via the command above. Service URL:
`https://mnlcc-api-1062400256329.us-central1.run.app`. All endpoints verified working against
all 7 layers (EE auth via ADC confirmed, all GEE assets finished ingesting).

**Bug found and fixed during initial verification:** `/tiles/{layer_id}` and `/value/{layer_id}`
originally only caught `ValueError`, not `ee.ee_exception.EEException` (e.g. a missing/not-yet-
ingested asset). An uncaught exception bypasses `CORSMiddleware` entirely — Starlette's
`ServerErrorMiddleware` wraps *outside* it — so the resulting 500 had no
`Access-Control-Allow-Origin` header. The browser treated this as a CORS failure rather than a
normal failed response, `fetch()` threw inside the frontend's layer-registration loop, and
because `prob_lgbm` was both first in `layers.json` and (at the time) still mid-ingest, the
*entire* `loadLayers()` call died before any layer got registered — the app showed only
basemaps, even though most layers were actually fine. A plain `curl -o /dev/null -w "%{http_code}"`
check per endpoint missed this, since it only tested status codes, not headers on the error path.
Fixed by catching `EEException` and converting it to `HTTPException` (which does flow through
`CORSMiddleware`), plus making the frontend skip default-visible layers that fail to register
instead of crashing the whole loop.

## Environment Variables

```text
GEE_PROJECT_ID=ee-jeli0026
CORS_ORIGINS=http://127.0.0.1:5500,http://localhost:5500
```

Do not commit `.env`.

## Earth Engine Authentication

Local development uses the `earthengine authenticate` persistent user token
(`~/.config/earthengine/credentials`). Production (Cloud Run) uses Application Default
Credentials via the attached service account — see `_init_earth_engine()` in `backend/app.py`,
which tries ADC first and falls back to the local user token.

## Deployment Checklist (all done)

1. ~~Confirm all 7 GEE assets are `COMPLETED`~~ — done, all 7 `COMPLETED` and readable by
   `mnlcc-api-runner` within `ee-jeli0026` (see `_ancillary/claude-chat-16SEP2026.md`).
2. ~~Push this repo to `origin`~~ — done.
3. ~~Create `mnlcc-api-runner` service account with the IAM roles above~~ — done.
4. ~~`gcloud run deploy`~~ — done. URL: `https://mnlcc-api-1062400256329.us-central1.run.app`.
5. ~~Test `/health`, `/layers`, `/tiles/{layer_id}`, `/value/{layer_id}`~~ — done, all 7 raw
   layers + both reference overlays verified serving tiles correctly.
6. ~~Update `frontend/config.js` `API_BASE`~~ — done.
7. ~~Create Cloudflare Pages project connected to this repo~~ — done. Branch `main`, build
   output directory `frontend`.
8. ~~Add custom domain~~ — done. `maps.mnlowlandconifercarbon.org` is `Active` with SSL
   (required a manual CNAME add — see Frontend section above).
9. ~~`CORS_ORIGINS` includes the production domain~~ — done, set at initial deploy.
10. ~~Verify end to end~~ — done at `https://maps.mnlowlandconifercarbon.org`. Also caught and
    fixed the CORS/EEException bug described above during this step.

Both sides redeploy automatically on push to `main` going forward — mostly. Cloudflare Pages
watches the GitHub connection directly and redeploys on every push. Cloud Run does **not**
auto-redeploy on push (no Cloud Build trigger is set up) — a code change to `backend/` needs a
fresh `gcloud run deploy` (the command above, run from `07-mnlcc-viewer/`) to go live.
