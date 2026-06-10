# Government Dashboard API Notes

The government dashboard in `web/` calls the backend under `/government`. Merchant endpoints under `/auth` and `/merchant` are not used by this dashboard.

## Authentication

Local demonstration auto-login reads these Vite environment variables:

```powershell
$env:VITE_DEMO_GOVERNMENT_EMAIL = "gov.admin@example.com"
$env:VITE_DEMO_GOVERNMENT_PASSWORD = "use-the-demo-password-from-backend-app-seed"
```

The demo account is seeded by `backend/app/seed.py`. The password is intentionally not hard-coded in `web/src/api.ts`.

## Endpoints Used

- `POST /government/auth/login`
- `GET /government/web/monthly-usage`
- `GET /government/web/enterprise-counts`
- `GET /government/web/region-distribution`
- `GET /government/web/top-stores`
- `GET /government/web/stores`

See `backend/API_USAGE.md` for request and response details.
