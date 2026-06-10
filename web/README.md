# Markerthon Government Dashboard

## Overview

`web/` is the government-facing Vite dashboard. It reads aggregate reusable-container metrics from the backend and displays monthly usage, enterprise counts, regional distribution, top stores, and store detail data.

This app talks only to `/government` endpoints.

## Requirements

- Node.js and npm.
- A running backend API from `backend/`.
- Seeded government demo account data from `backend/app/seed.py` for local demonstration.

## Configuration

Set the backend base URL:

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
```

The dashboard can auto-login for local demonstration when both environment variables are provided:

```powershell
$env:VITE_DEMO_GOVERNMENT_EMAIL = "gov.admin@example.com"
$env:VITE_DEMO_GOVERNMENT_PASSWORD = "use-the-demo-password-from-backend-app-seed"
```

The auto-login password is intentionally not hard-coded in frontend source. Demo credentials are for local demonstration only and are defined in `backend/app/seed.py`.

## Run

Install dependencies and start the Vite dev server from `web/`:

```powershell
npm install
npm run dev
```

The default dev URL is:

```text
http://127.0.0.1:5174
```

The repository launcher can also start this dashboard from the repository root:

```powershell
$env:JWT_SECRET = "replace-with-a-local-random-value"
python run.py --web-only
```

## Build

Create a local production build:

```powershell
npm run build
```

Generated output goes to the dist directory, which is ignored and should be regenerated locally.

## API Contract

The dashboard uses:

- `POST /government/auth/login`
- `GET /government/web/monthly-usage`
- `GET /government/web/enterprise-counts`
- `GET /government/web/region-distribution`
- `GET /government/web/top-stores`
- `GET /government/web/stores`

The API client lives in `web/src/api.ts`; backend route details are documented in `backend/API_USAGE.md`.
