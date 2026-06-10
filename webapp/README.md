# Markerthon Merchant Web App

## Overview

`webapp/` is the merchant-facing Vite React application. It supports merchant login, merchant registration, QR batch creation, QR return scanning, and sold/recovered statistics for the authenticated store.

This app talks to the backend endpoints under `/auth` and `/merchant`.

## Requirements

- Node.js and npm.
- A running backend API from `backend/`.
- Seeded demo accounts from `backend/app/seed.py` when using the sample login emails.

## Configuration

Set the backend base URL with `VITE_API_BASE_URL`. If it is not set, the app uses `http://127.0.0.1:8000`.

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
```

Demo accounts are for local demonstration only. The demo users and password are centralized in `backend/app/seed.py`.

## Run

Install dependencies and start the Vite dev server from `webapp/`:

```powershell
npm install
npm run dev
```

The default dev URL is:

```text
http://127.0.0.1:5173
```

The repository launcher can also start this app from the repository root:

```powershell
$env:JWT_SECRET = "replace-with-a-local-random-value"
python run.py --webapp-only
```

## Build

Create a local production build:

```powershell
npm run build
```

Generated output goes to the dist directory, which is ignored and should be regenerated locally.

## API Contract

The merchant app uses:

- `POST /auth/login`
- `POST /auth/register`
- `GET /auth/stores/region`
- `PATCH /merchant/store/region`
- `POST /merchant/qr-codes`
- `POST /merchant/returns/scan`
- `GET /merchant/stats/sold`
- `GET /merchant/stats/recovered`

The typed client lives in `webapp/src/api/client.ts`; backend route details are documented in `backend/API_USAGE.md`.
