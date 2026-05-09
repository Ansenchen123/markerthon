# 循環取還後端 MVP

FastAPI + SQLite backend for the reusable cup / meal-box deposit return demo.

## Setup

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

| Store | User Email | Password |
|---|---|---|
| 青山茶飲 | `tea.owner@example.com` | `password123` |
| 青山茶飲 | `tea.staff@example.com` | `password123` |
| 晨光便當 | `bento.owner@example.com` | `password123` |
| 巷口咖啡 | `cafe.owner@example.com` | `password123` |
| 政府端管理 | `gov.admin@example.com` | `password123` |

## Main Merchant APIs

- `POST /auth/register`
- `POST /auth/login`
- `POST /merchant/qr-codes`
- `POST /merchant/returns/scan`
- `GET /merchant/stats/sold`
- `GET /merchant/stats/recovered`
- `POST /government/auth/register`
- `POST /government/auth/login`
- `GET /government/overview`
- `GET /government/stores`
- `GET /government/daily/sold`
- `GET /government/daily/recovered`
- `GET /government/invoices`
- `GET /government/invoices/{loanId}`
- `GET /government/anomalies`

The QR value returned by `/merchant/qr-codes` is a one-time loan credential formatted as:

```text
<invoiceCode>|<storeCode>
```

Example: `INV-20260509-001|tea-shop`.

Each invoice has only one QR code per store. `POST /merchant/qr-codes` accepts `invoiceCode` and `cupCount`; repeated calls for the same store and invoice reuse the same QR value and increase the backend count. Each scan return decreases the backend remaining count by one cup.

Daily sold and recovered reports are append-only CSV logs. Each successful QR creation appends a `sold` row, and each successful scan return appends a `recovered` row to that day's CSV file.
