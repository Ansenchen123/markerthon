# Markerthon API Usage

Base URL for local development:

```text
http://127.0.0.1:8000
```

Interactive documentation:

```text
http://127.0.0.1:8000/docs
```

Set `JWT_SECRET` before starting the backend. Startup intentionally fails if it is missing.

## Demo Data

Demo users are local demonstration accounts only. They are seeded by `app/seed.py`, and the single demo password is centralized there as `DEMO_PASSWORD`.

Seeded emails:

- `tea.owner@example.com`
- `tea.staff@example.com`
- `bento.owner@example.com`
- `cafe.owner@example.com`
- `gov.admin@example.com`

## Authentication

Authenticated merchant and government endpoints use a bearer token:

```http
Authorization: Bearer <access token>
```

Merchant tokens can call `/merchant` endpoints. Government tokens can call `/government` endpoints. The two roles are not interchangeable.

## Health

### GET `/health`

Response `200`:

```json
{
  "status": "ok"
}
```

## Merchant Auth

### GET `/auth/stores/region`

Looks up an existing store region by store name.

Query:

| Name | Required | Notes |
|---|---|---|
| `storeName` | yes | Non-empty store name |

Response `200`:

```json
{
  "storeName": "Demo Store",
  "region": "Demo Region"
}
```

Failure:

| Status | Meaning |
|---:|---|
| 404 | Store was not found |

### POST `/auth/register`

Creates a merchant user and store when needed.

Request:

```json
{
  "userEmail": "new.merchant@example.test",
  "password": "<password>",
  "storeName": "Demo Store",
  "region": "Demo Region"
}
```

Response `201`:

```json
{
  "accessToken": "<jwt>",
  "tokenType": "bearer",
  "store": {
    "id": 4,
    "code": "store-a1b2c3d4",
    "name": "Demo Store",
    "region": "Demo Region"
  }
}
```

Failure:

| Status | Meaning |
|---:|---|
| 409 | Email already exists |
| 422 | Invalid email or password length |

### POST `/auth/login`

Logs in a merchant user.

Request:

```json
{
  "userEmail": "tea.owner@example.com",
  "password": "<demo password>"
}
```

Response `200`:

```json
{
  "accessToken": "<jwt>",
  "tokenType": "bearer",
  "store": {
    "id": 1,
    "code": "tea-shop",
    "name": "Seeded Store",
    "region": "Seeded Region"
  }
}
```

Failure:

| Status | Meaning |
|---:|---|
| 401 | Invalid email or password |
| 422 | Invalid email format |

## Merchant APIs

### PATCH `/merchant/store/region`

Updates the authenticated merchant store region.

Request:

```json
{
  "region": "Updated Demo Region"
}
```

Response `200`:

```json
{
  "id": 1,
  "code": "tea-shop",
  "name": "Seeded Store",
  "region": "Updated Demo Region"
}
```

### POST `/merchant/qr-codes`

Creates or extends a QR-backed loan for the authenticated merchant store. A repeated store, invoice, and category combination reuses the same QR value and increases the counts.

Request:

```json
{
  "invoiceCode": "INV-DEMO-001",
  "category": "cup",
  "count": 2
}
```

Allowed `category` values are `cup` and `meal_box`. `count` must be 1 through 100.

Response `201`:

```json
{
  "loanId": 1,
  "qrValue": "INV-DEMO-001|tea-shop|cup",
  "invoiceCode": "INV-DEMO-001",
  "storeCode": "tea-shop",
  "category": "cup",
  "addedCount": 2,
  "totalCount": 2,
  "returnedCount": 0,
  "remainingCount": 2,
  "issuedAt": "2026-05-09T12:05:32",
  "dueAt": "2026-05-12T12:05:32"
}
```

Database behavior:

| Table | Change |
|---|---|
| `loans` | Stores cumulative `item_count`, current `remaining_count`, category, deposit amount, and a SHA-256 `qr_token_hash`; it does not store the plain QR value |
| Daily CSV | Appends one `sold` row through `append_sold_report_row` |

### POST `/merchant/returns/scan`

Scans one returned container for the authenticated merchant store.

Request:

```json
{
  "qrValue": "INV-DEMO-001|tea-shop|cup"
}
```

Response `200`:

```json
{
  "accepted": true,
  "loanId": 1,
  "status": "partial_returned",
  "category": "cup",
  "invoiceCode": "INV-DEMO-001",
  "issuedStoreId": 1,
  "returnedStoreId": 1,
  "count": 1,
  "totalCount": 2,
  "returnedCount": 1,
  "remainingCount": 1,
  "refundReason": "normal",
  "isExpired": false,
  "isAbnormal": false,
  "dueAt": "2026-05-12T12:05:32",
  "returnedAt": "2026-05-09T12:10:00"
}
```

Failure:

| Status | Meaning | Database change |
|---:|---|---|
| 404 | QR value was not found | Adds a `scan_events` row with `result=invalid_qr` |
| 409 | QR has already been fully returned | Adds a `scan_events` row with `result=duplicate_scan` |

Database behavior:

| Table | Change |
|---|---|
| `loans` | Increments `returned_count`, decrements `remaining_count`, updates status, return store, and return time |
| `refund_ledgers` | Adds or updates the refund amount and reason |
| `scan_events` | Adds one scan result row |
| Daily CSV | Appends one `recovered` row through `append_recovered_report_row` |

### GET `/merchant/stats/sold`

Returns daily sold counts for the authenticated merchant store.

Query:

| Name | Required | Notes |
|---|---|---|
| `storeId` | yes | Must match the store in the merchant token |
| `from` | yes | ISO date |
| `to` | yes | ISO date |

Response `200`:

```json
{
  "storeId": 1,
  "storeName": "Seeded Store",
  "from": "2026-05-08",
  "to": "2026-05-10",
  "remainingCount": 1,
  "rows": [
    {
      "statDate": "2026-05-09",
      "totalCount": 1,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 1
        }
      ]
    }
  ]
}
```

Failure:

| Status | Meaning |
|---:|---|
| 400 | `from` is after `to` |
| 403 | Requested store does not match the merchant token |

### GET `/merchant/stats/recovered`

Returns daily recovered counts for the authenticated merchant store.

Query:

| Name | Required | Notes |
|---|---|---|
| `storeId` | yes | Must match the store in the merchant token |
| `from` | yes | ISO date |
| `to` | yes | ISO date |

Response `200`:

```json
{
  "storeId": 1,
  "storeName": "Seeded Store",
  "from": "2026-05-08",
  "to": "2026-05-10",
  "rows": [
    {
      "statDate": "2026-05-09",
      "totalCount": 1,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 1
        }
      ],
      "normalCount": 1,
      "expiredCount": 0,
      "abnormalCount": 0,
      "crossStoreCount": 0
    }
  ]
}
```

Failure:

| Status | Meaning |
|---:|---|
| 400 | `from` is after `to` |
| 403 | Requested store does not match the merchant token |

## Government Auth

### POST `/government/auth/register`

Creates a government user.

Request:

```json
{
  "userEmail": "new.gov@example.test",
  "password": "<password>"
}
```

Response `201`:

```json
{
  "accessToken": "<jwt>",
  "tokenType": "bearer",
  "user": {
    "id": 2,
    "userEmail": "new.gov@example.test"
  }
}
```

Failure:

| Status | Meaning |
|---:|---|
| 409 | Email already exists |
| 422 | Invalid email or password length |

### POST `/government/auth/login`

Logs in a government user.

Request:

```json
{
  "userEmail": "gov.admin@example.com",
  "password": "<demo password>"
}
```

Response `200`:

```json
{
  "accessToken": "<jwt>",
  "tokenType": "bearer",
  "user": {
    "id": 1,
    "userEmail": "gov.admin@example.com"
  }
}
```

## Government Web APIs

All endpoints in this section require a government bearer token.

### GET `/government/web/monthly-usage`

Query:

| Name | Required | Notes |
|---|---|---|
| `year` | no | 2000 through 2100 |
| `month` | no | 1 through 12 |

Response `200` includes `month`, `from`, `to`, `issuedCount`, `returnedCount`, `remainingCount`, `recoveryRate`, invoice status counts, `overdueCount`, `abnormalCount`, and a `daily` array.

### GET `/government/web/enterprise-counts`

Query:

| Name | Required | Notes |
|---|---|---|
| `year` | no | 2000 through 2100 |
| `month` | no | 1 through 12 |

Response `200` includes `monthJoinedCount` and `totalEnterpriseCount`.

### GET `/government/web/region-distribution`

Response `200` includes `totalEnterpriseCount` and a `regions` array of `region` and `enterpriseCount`.

### GET `/government/web/top-stores`

Query:

| Name | Required | Notes |
|---|---|---|
| `year` | no | 2000 through 2100 |
| `month` | no | 1 through 12 |
| `limit` | no | 1 through 100; default is 10 |

Response `200` includes `month`, `from`, `to`, and `rankings`. Each ranking row includes store identity, issued count, returned count, remaining count, and recovery rate.

### GET `/government/web/stores`

Query:

| Name | Required | Notes |
|---|---|---|
| `storeName` | yes | Store name to look up |
| `year` | no | 2000 through 2100 |
| `month` | no | 1 through 12 |

Response `200` includes store identity, issued count, returned count, recovered count, remaining count, recovery rate, category counts, overdue count, abnormal count, cross-store recovered count, and `lastActivityAt`.

Failure:

| Status | Meaning |
|---:|---|
| 404 | Store was not found |

## Daily CSV Reports

Successful merchant QR creation appends `sold` rows. Successful return scans append `recovered` rows.

Default directory:

```text
data/daily_reports/
```

Default filename:

```text
daily_report_YYYY-MM-DD.csv
```

Important columns include `eventType`, `occurredAt`, `loanId`, `invoiceCode`, `qrValue`, store identity fields, `category`, `count`, `totalCount`, `returnedCount`, `remainingCount`, `condition`, `result`, `reason`, `isExpired`, `isAbnormal`, and `isCrossStore`.
