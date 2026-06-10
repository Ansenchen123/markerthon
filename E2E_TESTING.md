# Local End-to-End Testing Notes

These notes describe how to exercise the backend, merchant frontend, and government dashboard together on a local machine.

## Backend Setup

From `backend/`, use an isolated local database and report directory:

```powershell
$env:DATABASE_URL = "sqlite:///./data/e2e.db"
$env:DAILY_REPORT_DIR = "./data/e2e_reports"
$env:JWT_SECRET = "replace-with-a-local-e2e-secret"
python -m app.seed
uvicorn app.main:app --host 127.0.0.1 --port 8013
```

Health check:

```powershell
curl http://127.0.0.1:8013/health
```

## Merchant Flow

1. Log in as a seeded merchant user from `backend/app/seed.py`.
2. Create a QR batch with `POST /merchant/qr-codes`.
3. Scan the returned QR with `POST /merchant/returns/scan`.
4. Confirm duplicate scans return `409`.
5. Confirm invalid QR values return `404`.
6. Confirm `/merchant/stats/sold` and `/merchant/stats/recovered` match the daily CSV rows.

## Government Flow

1. Log in with the seeded government user from `backend/app/seed.py`.
2. Query `/government/web/monthly-usage`.
3. Query `/government/web/enterprise-counts`.
4. Query `/government/web/region-distribution`.
5. Query `/government/web/top-stores`.
6. Query `/government/web/stores` with a seeded store name.

## Validation Points

- Merchant stat requests must use a `storeId` that matches the merchant token, otherwise the backend returns `403`.
- Government tokens must not call merchant endpoints.
- Merchant tokens must not call government endpoints.
- `loans.item_count` stays cumulative.
- `loans.remaining_count` decreases by one for every successful return scan.
- Daily CSV totals should match the corresponding API aggregate totals for the same date range.
- The government dashboard should use only `/government/web/...` endpoints.
