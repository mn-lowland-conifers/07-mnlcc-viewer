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

**Status: not yet deployed.** Production domain: `maps.mnlowlandconifercarbon.org`, a zone Nic
already owns and manages on Cloudflare (DNS only so far — no Pages project or backend yet). This
document describes the intended setup; fill in the remaining TODOs as each step is completed.

## Frontend

Static files, no build step:

```text
frontend/index.html
frontend/app.js
frontend/style.css
frontend/config.js
```

`frontend/config.js` sets `API_BASE`, which must point at the deployed Cloud Run URL in
production. Local dev default:

```javascript
window.MNLCC_CONFIG = {
  API_BASE: "http://127.0.0.1:8000"
};
```

Custom domain: **`maps.mnlowlandconifercarbon.org`** (Cloudflare — same account already holds
the zone, so no DNS registrar changes needed, only the Pages setup below).

TODO once deployed:
- Update `API_BASE` to the live Cloud Run URL

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

TODO:
- Create service account `mnlcc-api-runner@ee-jeli0026.iam.gserviceaccount.com` and grant:
  - `roles/earthengine.writer` (not `viewer` — tile map ID generation needs the writer role's
    permission set; confirmed the hard way on askdb-viewer)
  - `roles/serviceusage.serviceUsageConsumer`
- Confirm Cloud Run Admin API / Cloud Build API / Artifact Registry API are enabled on
  `ee-jeli0026` (already true if askdb-viewer's Cloud Run setup is live on the same project)

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

1. Confirm all 7 GEE assets are `COMPLETED` and public (see the ingest handoff doc,
   `claude-chat-16SEP2026.md`, at the repo root).
2. Push this repo to `origin` (`mn-lowland-conifers/07-mnlcc-viewer` on GitHub) — the repo has no
   commits yet, and Cloudflare Pages deploys from the GitHub connection, not a local push.
3. Create `mnlcc-api-runner` service account with the IAM roles above (one-time, in the GCP
   Console or via `gcloud iam service-accounts create`).
4. `gcloud run deploy` per the command above (from `07-mnlcc-viewer/`). Note the resulting
   `*.run.app` URL.
5. Test `/health`, `/layers`, `/tiles/{layer_id}`, `/value/{layer_id}` against that URL.
6. Update `frontend/config.js` `API_BASE` to the live Cloud Run URL; commit and push.
7. In the Cloudflare dashboard: **Workers & Pages → Create application → Pages → Connect to
   Git** → select `mn-lowland-conifers/07-mnlcc-viewer`, branch `main`. Build settings:
   framework preset **None**, no build command, **build output directory: `frontend`** (the
   site lives in a subdirectory, not the repo root). Save and deploy.
8. In the new Pages project: **Custom domains → Add a custom domain** →
   `maps.mnlowlandconifercarbon.org`. Since the zone is already on this Cloudflare account, the
   CNAME is added automatically — no registrar/DNS changes needed. HTTPS provisions
   automatically too.
9. Back on Cloud Run, redeploy with `CORS_ORIGINS` including
   `https://maps.mnlowlandconifercarbon.org` (already in the command above).
10. Verify end to end at `https://maps.mnlowlandconifercarbon.org`.

After this initial setup, both sides redeploy automatically on push to `main`: Cloudflare Pages
watches the GitHub connection directly, and Cloud Run needs a new `gcloud run deploy` (not
auto-triggered unless a Cloud Build trigger is set up separately).
