# Markerthon Backend API

FastAPI and SQLite backend for reusable container issuing, return scanning, daily report generation, and government dashboard APIs.

## Setup

From the repository root:

```powershell
cd backend
python -m pip install -r requirements.txt
cd ..
$env:JWT_SECRET = "replace-with-a-local-random-value"
python run.py --backend-only --seed
```

Manual backend startup from `backend/`:

```powershell
$env:JWT_SECRET = "replace-with-a-local-random-value"
python -m app.seed
uvicorn app.main:app --reload
```

Default database path: `data/reusable_container.db`.
Default daily CSV report path: `data/daily_reports/daily_report_YYYY-MM-DD.csv`.

## Demo Accounts

Demo accounts are local demonstration data only. Seeded users are defined in `app/seed.py`, and the single demo password is centralized as `DEMO_PASSWORD`.

Seeded emails:

- `tea.owner@example.com`
- `tea.staff@example.com`
- `bento.owner@example.com`
- `cafe.owner@example.com`
- `gov.admin@example.com`

## Main APIs

- `GET /health`
- `GET /auth/stores/region`
- `POST /auth/register`
- `POST /auth/login`
- `PATCH /merchant/store/region`
- `POST /merchant/qr-codes`
- `POST /merchant/returns/scan`
- `GET /merchant/stats/sold`
- `GET /merchant/stats/recovered`
- `POST /government/auth/register`
- `POST /government/auth/login`
- `GET /government/web/monthly-usage`
- `GET /government/web/enterprise-counts`
- `GET /government/web/region-distribution`
- `GET /government/web/top-stores`
- `GET /government/web/stores`

Full request and response details are in `API_USAGE.md`.

## Tests

```powershell
$env:JWT_SECRET = "replace-with-a-local-test-value"
python -m pytest tests
```
