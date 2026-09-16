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

**Status: backend live, frontend not yet deployed.** Production domain:
`maps.mnlowlandconifercarbon.org`, a zone Nic already owns and manages on Cloudflare (DNS only
so far — no Pages project yet).

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

Custom domain: **`maps.mnlowlandconifercarbon.org`** (Cloudflare — same account already holds
the zone, so no DNS registrar changes needed, only the Pages setup below).

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
`https://mnlcc-api-1062400256329.us-central1.run.app`. `/health` and `/layers` verified working
(EE auth via ADC confirmed). `/tiles/{layer_id}` will 500 with "Image asset ... not found" for
any layer whose GEE asset hasn't finished ingesting yet — not a backend bug, just ingest status;
see `claude-chat-16SEP2026.md`.

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

## Deployment Checklist

1. ~~Confirm all 7 GEE assets are `COMPLETED`~~ — 5 of 7 `COMPLETED`, 2 `RUNNING` as of
   2026-09-16. Public ACLs not yet confirmed set (see `claude-chat-16SEP2026.md`).
2. ~~Push this repo to `origin`~~ — done.
3. ~~Create `mnlcc-api-runner` service account with the IAM roles above~~ — done.
4. ~~`gcloud run deploy`~~ — done. URL: `https://mnlcc-api-1062400256329.us-central1.run.app`.
5. ~~Test `/health`, `/layers`~~ — both verified working. `/tiles/{layer_id}` /
   `/value/{layer_id}` to be reverified once all 7 assets finish ingesting.
6. ~~Update `frontend/config.js` `API_BASE`~~ — done.
7. **Next:** in the Cloudflare dashboard: **Workers & Pages → Create application → Pages →
   Connect to Git** → select `mn-lowland-conifers/07-mnlcc-viewer`, branch `main`. Build
   settings: framework preset **None**, no build command, **build output directory: `frontend`**
   (the site lives in a subdirectory, not the repo root). Save and deploy.
8. In the new Pages project: **Custom domains → Add a custom domain** →
   `maps.mnlowlandconifercarbon.org`. Since the zone is already on this Cloudflare account, the
   CNAME is added automatically — no registrar/DNS changes needed. HTTPS provisions
   automatically too.
9. `CORS_ORIGINS` already includes `https://maps.mnlowlandconifercarbon.org` from step 4 — no
   backend redeploy needed for this unless the domain changes.
10. Once the last 2 GEE assets finish ingesting, verify end to end at
    `https://maps.mnlowlandconifercarbon.org`.

After this initial setup, both sides redeploy automatically on push to `main`: Cloudflare Pages
watches the GitHub connection directly, and Cloud Run needs a new `gcloud run deploy` (not
auto-triggered unless a Cloud Build trigger is set up separately).
