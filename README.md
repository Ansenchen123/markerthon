# 循環取還後端 MVP

FastAPI + SQLite backend for the reusable cup / meal-box deposit return demo.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

Default database path: `data/reusable_container.db`.

## Demo Accounts

| Store | Username | Password |
|---|---|---|
| 青山茶飲 | `tea_owner` | `password123` |
| 晨光便當 | `bento_owner` | `password123` |
| 巷口咖啡 | `cafe_owner` | `password123` |

## Main Merchant APIs

- `POST /auth/login`
- `POST /merchant/qr-codes`
- `POST /merchant/returns/scan`
- `GET /merchant/stats/sold`
- `GET /merchant/stats/recovered`

The QR value returned by `/merchant/qr-codes` is a one-time loan credential formatted as:

```text
<invoiceCode>|<storeCode>
```

Example: `INV-20260509-001|tea-shop`.

Each invoice has only one QR code per store. `POST /merchant/qr-codes` accepts `invoiceCode` and `cupCount`; repeated calls for the same store and invoice reuse the same QR value and increase the backend count. Each scan return decreases the backend remaining count by one cup.
