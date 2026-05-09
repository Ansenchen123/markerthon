# 循環取還後端 MVP

FastAPI + SQLite backend for the reusable cup / meal-box deposit return demo.

## Setup

From the repository root, the least ambiguous way to start the full local system is:

```bash
python3 run.py --seed
```

Or:

```bash
./run.py --seed
```

This starts the backend at `http://127.0.0.1:8000` and the merchant web app at `http://127.0.0.1:5173`.
Use `python3 run.py --backend-only --seed` when you only need the backend.

Or start it manually from this `backend/` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
python -m app.demo_data
uvicorn app.main:app --reload
```

Default database path: `data/reusable_container.db`.
Default daily CSV report path: `data/daily_reports/daily_report_YYYY-MM-DD.csv`.
`python -m app.demo_data` creates a realistic five-day demo flow through the normal APIs and only fakes backend time so past-dated CSV files are produced.

## Demo Accounts

| Store | Region | User Email | Password |
|---|---|---|---|
| 青山茶飲 | 台北市大安區 | `tea.owner@example.com` | `password123` |
| 青山茶飲 | 台北市大安區 | `tea.staff@example.com` | `password123` |
| 晨光便當 | 台北市中山區 | `bento.owner@example.com` | `password123` |
| 巷口咖啡 | 新北市板橋區 | `cafe.owner@example.com` | `password123` |
| 政府端管理 | - | `gov.admin@example.com` | `password123` |

## Main Merchant APIs

- `POST /auth/register`
- `POST /auth/login`
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
- `GET /government/web/stores?storeName=<name>`

The QR value returned by `/merchant/qr-codes` is a one-time loan credential formatted as:

```text
<invoiceCode>|<storeCode>|<category>
```

Example: `INV-20260509-001|tea-shop|cup`.

Each invoice has one QR code per store and category label. `POST /merchant/qr-codes` accepts `invoiceCode`, `category`, and `count`; repeated calls for the same store, invoice, and category reuse the same QR value and increase the backend count. If the same invoice contains both cups and meal boxes, each category gets its own QR value. Each scan return decreases that QR's backend remaining count by one container.

Daily sold and recovered reports are append-only CSV logs. Each successful QR creation appends a `sold` row, and each successful scan return appends a `recovered` row to that day's CSV file. Merchant stats APIs require `storeName`, verify it matches the merchant JWT, aggregate these CSV logs by date, return one row per requested day, and expose per-category counts through `categoryCounts`. Merchant sold stats also return the current `remainingCount` from `loans.remaining_count`, because "issued by this store but not yet returned" is not the same as "issued by this store minus scanned by this store" when cross-store returns exist. Government web APIs use the database to provide the current monthly dashboard and store status. In `loans`, `item_count` keeps the cumulative issued total, while `remaining_count` is decremented by one on every successful return scan.
