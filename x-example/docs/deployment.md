# AKSDB Explorer Deployment Notes

## Target Production Architecture

```text
User browser
  ↓
CloudFront / S3 static frontend
  ↓
EC2 backend API
  ↓
Google Earth Engine
```

## Frontend

The frontend is static and can be hosted from:

- S3
- CloudFront
- GitHub Pages for testing
- Any static web server

Production frontend files:

```text
frontend/index.html
frontend/app.js
frontend/style.css
```

The frontend must point `API_BASE` to the production backend API URL.

Local:

```javascript
const API_BASE = "http://127.0.0.1:8000";
```

Production example:

```javascript
const API_BASE = "https://api.aksdb.org";
```

## Backend

The backend is a FastAPI application.

Production entry point:

```text
backend/app.py
```

Run locally:

```bash
cd backend
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8000
```

Production EC2 target:

```text
Ubuntu EC2
Python virtual environment
FastAPI
Uvicorn
Nginx reverse proxy
HTTPS certificate
Earth Engine authentication
```

## Environment Variables

The backend uses:

```text
GEE_PROJECT_ID
CORS_ORIGINS
```

Example `.env`:

```text
GEE_PROJECT_ID=ee-jeli0026
CORS_ORIGINS=http://127.0.0.1:5500,http://localhost:5500
```

Production example:

```text
GEE_PROJECT_ID=ee-jeli0026
CORS_ORIGINS=https://maps.aksdb.org,https://aksdb.org
```

Do not commit `.env`.

## Earth Engine Authentication

Local development currently uses user authentication from:

```bash
earthengine authenticate
```

Production should use a Google service account with access to the Earth Engine project and required image assets.

Service account credential files must never be committed to Git.

## Deployment Steps

1. Launch EC2 instance.
2. Install system packages.
3. Clone repository.
4. Create Python virtual environment.
5. Install backend requirements.
6. Configure `.env`.
7. Configure Earth Engine service account.
8. Start backend with Uvicorn.
9. Place backend behind Nginx.
10. Configure HTTPS.
11. Upload frontend to S3.
12. Put CloudFront in front of S3.
13. Update frontend `API_BASE`.
14. Update backend `CORS_ORIGINS`.
15. Test `/health`, `/layers`, `/tiles/{layer_id}`, and `/value/{layer_id}`.

## Future Production Additions

- Postgres/PostGIS
- observation submission API
- authentication
- rate limiting
- logging
- monitoring
- automated deployment
