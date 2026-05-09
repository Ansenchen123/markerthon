# 循環取還 API 使用說明

Base URL for local development:

```text
http://127.0.0.1:8000
```

Interactive docs:

```text
http://127.0.0.1:8000/docs
```

## 啟動與測試帳號

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

Demo accounts:

| Store | User Email | Password |
|---|---|---|
| 青山茶飲 | `tea.owner@example.com` | `password123` |
| 青山茶飲 | `tea.staff@example.com` | `password123` |
| 晨光便當 | `bento.owner@example.com` | `password123` |
| 巷口咖啡 | `cafe.owner@example.com` | `password123` |
| 政府端管理 | `gov.admin@example.com` | `password123` |

## Auth

除了登入以外，商家 API 都要帶 JWT：

```http
Authorization: Bearer <accessToken>
```

### POST `/auth/register`

商家註冊，會同時建立店家資料與商家帳號。`storeCode` 由後端自動產生，前端不需要傳。若 `storeName` 已存在，新的 `userEmail` 會綁到同一家店；`userEmail` 全系統唯一。註冊成功後直接回傳 JWT。

Request:

```json
{
  "userEmail": "new.merchant@example.com",
  "password": "password123",
  "storeName": "新店家"
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
    "name": "新店家"
  }
}
```

Failure:

| Status | Meaning |
|---:|---|
| 409 | Email 已存在 |
| 422 | 欄位格式不符合，例如 email 格式錯誤或密碼少於 8 碼 |

### POST `/auth/login`

商家登入，成功後回傳 JWT 與商家資料。

Request:

```json
{
  "userEmail": "tea.owner@example.com",
  "password": "password123"
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
    "name": "青山茶飲"
  }
}
```

Failure:

| Status | Meaning |
|---:|---|
| 401 | Email 或密碼錯誤 |
| 422 | Email 格式錯誤 |

## 四個主要商家 API

### 1. POST `/merchant/qr-codes`

店家賣出循環杯時呼叫。店家只需要輸入發票號碼與杯數，後端會依「商家 + 發票」找到同一筆發票紀錄並累加 `cupCount`。同一張發票只會有一個 `qrValue`；前端只需要把這個 `qrValue` 生成一張 QR Code 圖。

QR 代表本次借出憑證，不代表實體容器 ID。容器本身不綁定識別碼。

`qrValue` 格式：

```text
<invoiceCode>|<storeCode>
```

例如同一家店同一張發票有兩杯飲料，只會產生：

```text
INV-20260509-001|tea-shop
```

杯數差異由後端 `cupCount` / `returnedCount` / `remainingCupCount` 記錄，不在 QR 裡區分單杯。

Request:

```json
{
  "invoiceCode": "INV-20260509-001",
  "cupCount": 2
}
```

`cupCount` 最小為 `1`，最大為 `100`。押金由後端內部帳本處理，不在商家 API 回傳。

Response `201`:

```json
{
  "loanId": 1,
  "qrValue": "INV-20260509-001|tea-shop",
  "invoiceCode": "INV-20260509-001",
  "storeCode": "tea-shop",
  "addedCupCount": 2,
  "totalCupCount": 2,
  "returnedCount": 0,
  "remainingCupCount": 2,
  "issuedAt": "2026-05-09T12:05:32.062579",
  "dueAt": "2026-05-12T12:05:32.062579"
}
```

DB changes:

| Table | Change |
|---|---|
| `loans` | 同店同發票不存在時新增一筆；已存在時更新同一筆 `cup_count += cupCount`，保存 `qr_token_hash`，不保存明文 `qrValue` |

### 2. POST `/merchant/returns/scan`

店家掃描 QR 回收容器時呼叫。掃描一次代表回收 1 杯，前端不需要輸入杯數。後端會累加 `returnedCount`，直到 `remainingCupCount` 為 0 才把狀態標記為 `returned`。

Request:

```json
{
  "qrValue": "INV-20260509-001|tea-shop",
  "condition": "normal",
  "note": "normal return"
}
```

`condition`:

| Value | Meaning |
|---|---|
| `normal` | 正常回收 |
| `damaged` | 破損 |
| `polluted` | 污染 |
| `other` | 其他異常 |

Response `200` for normal in-time return:

```json
{
  "accepted": true,
  "loanId": 1,
  "status": "returned",
  "containerType": "cup",
  "invoiceCode": "INV-20260509-001",
  "issuedStoreId": 1,
  "returnedStoreId": 1,
  "cupCount": 1,
  "totalCupCount": 2,
  "returnedCount": 1,
  "remainingCupCount": 1,
  "refundReason": "normal",
  "isExpired": false,
  "isAbnormal": false,
  "dueAt": "2026-05-12T12:05:32.062579",
  "returnedAt": "2026-05-09T12:05:32.066739"
}
```

Response `200` for expired or abnormal return:

```json
{
  "accepted": true,
  "loanId": 1,
  "status": "returned",
  "containerType": "cup",
  "invoiceCode": "INV-20260509-001",
  "issuedStoreId": 1,
  "returnedStoreId": 2,
  "cupCount": 1,
  "totalCupCount": 2,
  "returnedCount": 1,
  "remainingCupCount": 1,
  "refundReason": "expired",
  "isExpired": true,
  "isAbnormal": false,
  "dueAt": "2026-05-12T12:05:32.062579",
  "returnedAt": "2026-05-13T09:00:00"
}
```

Failure:

| Status | Meaning | DB change |
|---:|---|---|
| 404 | QR 不存在 | `scan_events` 新增 `result='invalid_qr'` |
| 409 | QR 已歸還，重複掃描 | `scan_events` 新增 `result='duplicate_scan'` |
DB changes on accepted return:

| Table | Change |
|---|---|
| `loans` | `returned_count += 1`；未全數回收為 `partial_returned`，全數回收為 `returned` |
| `refund_ledgers` | 內部累加退押帳本；不回傳金額給商家 API |
| `scan_events` | 新增掃碼事件，供異常統計與稽核 |

### 3. GET `/merchant/stats/sold`

查詢登入商家在時間區間內自己賣出多少循環杯/餐盒。

Query params:

| Name | Required | Example |
|---|---|---|
| `from` | yes | `2026-05-08T00:00:00` |
| `to` | yes | `2026-05-10T23:59:59` |
| `containerType` | no | `cup` or `meal_box` |

Example:

```http
GET /merchant/stats/sold?from=2026-05-08T00:00:00&to=2026-05-10T23:59:59&containerType=cup
Authorization: Bearer <accessToken>
```

Response `200`:

```json
{
  "storeId": 1,
  "from": "2026-05-08T00:00:00",
  "to": "2026-05-10T23:59:59",
  "containerType": "cup",
  "totalCount": 1,
  "cupCount": 1,
  "mealBoxCount": 0
}
```

DB read:

| Table | Filter |
|---|---|
| `loans` | `issued_store_id = current_store_id` and `issued_at` between `from` and `to` |

### 4. GET `/merchant/stats/recovered`

查詢登入商家在時間區間內自己回收多少循環杯/餐盒。

Query params:

| Name | Required | Example |
|---|---|---|
| `from` | yes | `2026-05-08T00:00:00` |
| `to` | yes | `2026-05-10T23:59:59` |
| `containerType` | no | `cup` or `meal_box` |

Example:

```http
GET /merchant/stats/recovered?from=2026-05-08T00:00:00&to=2026-05-10T23:59:59
Authorization: Bearer <accessToken>
```

Response `200`:

```json
{
  "storeId": 1,
  "from": "2026-05-08T00:00:00",
  "to": "2026-05-10T23:59:59",
  "containerType": null,
  "totalCount": 1,
  "normalCount": 1,
  "expiredCount": 0,
  "abnormalCount": 0,
  "crossStoreCount": 0
}
```

DB read:

| Table | Filter |
|---|---|
| `loans` | `returned_store_id = current_store_id` and `returned_at` between `from` and `to` |

## cURL 全流程範例

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"userEmail":"tea.owner@example.com","password":"password123"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')

QR_VALUE=$(curl -s -X POST http://127.0.0.1:8000/merchant/qr-codes \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"invoiceCode":"INV-DEMO-001","cupCount":2}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["qrValue"])')

curl -s -X POST http://127.0.0.1:8000/merchant/returns/scan \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"qrValue\":\"$QR_VALUE\",\"condition\":\"normal\",\"note\":\"demo return\"}"

curl -s "http://127.0.0.1:8000/merchant/stats/sold?from=2026-05-08T00:00:00&to=2026-05-10T23:59:59" \
  -H "Authorization: Bearer $TOKEN"

curl -s "http://127.0.0.1:8000/merchant/stats/recovered?from=2026-05-08T00:00:00&to=2026-05-10T23:59:59" \
  -H "Authorization: Bearer $TOKEN"
```

## 政府端 API

政府端 API 全部使用 `/government/...`，不和商家端 `/merchant/...` 混用。政府 token 不能呼叫商家 API，商家 token 也不能呼叫政府 API。

### POST `/government/auth/register`

政府端註冊，成功後直接回傳政府端 JWT。

Request:

```json
{
  "userEmail": "new.gov@example.com",
  "password": "password123"
}
```

Response `201`:

```json
{
  "accessToken": "<jwt>",
  "tokenType": "bearer",
  "user": {
    "id": 2,
    "userEmail": "new.gov@example.com"
  }
}
```

Failure:

| Status | Meaning |
|---:|---|
| 409 | Email 已存在 |
| 422 | 欄位格式不符合，例如 email 格式錯誤或密碼少於 8 碼 |

### POST `/government/auth/login`

Request:

```json
{
  "userEmail": "gov.admin@example.com",
  "password": "password123"
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

政府端查詢 API 都要帶：

```http
Authorization: Bearer <governmentAccessToken>
```

### GET `/government/overview`

政府首頁總覽。

Query params:

| Name | Required | Example |
|---|---|---|
| `from` | yes | `2026-05-08T00:00:00` |
| `to` | yes | `2026-05-10T23:59:59` |

Response `200`:

```json
{
  "from": "2026-05-08T00:00:00",
  "to": "2026-05-10T23:59:59",
  "issuedCupCount": 20,
  "returnedCupCount": 12,
  "remainingCupCount": 8,
  "recoveryRate": 0.6,
  "activeInvoiceCount": 4,
  "returnedInvoiceCount": 3,
  "partialReturnedInvoiceCount": 2,
  "overdueCupCount": 1,
  "abnormalCupCount": 1
}
```

### GET `/government/stores`

各店統計。

Query params: `from`, `to`

Response `200`:

```json
{
  "from": "2026-05-08T00:00:00",
  "to": "2026-05-10T23:59:59",
  "stores": [
    {
      "storeId": 1,
      "storeCode": "tea-shop",
      "storeName": "青山茶飲",
      "issuedCupCount": 10,
      "returnedCupCount": 6,
      "remainingCupCount": 4,
      "crossStoreReturnedCount": 2,
      "abnormalCupCount": 1,
      "recoveryRate": 0.6,
      "lastActivityAt": "2026-05-09T12:05:32.062579"
    }
  ]
}
```

### GET `/government/daily/sold`

每日賣出彙總，讀 `daily_sold_stats`。每一天、每店、每容器類型一列。

Query params:

| Name | Required | Example |
|---|---|---|
| `from` | yes | `2026-05-09` |
| `to` | yes | `2026-05-09` |
| `storeId` | no | `1` |
| `containerType` | no | `cup` |

Response `200`:

```json
{
  "from": "2026-05-09",
  "to": "2026-05-09",
  "rows": [
    {
      "statDate": "2026-05-09",
      "storeId": 1,
      "storeCode": "tea-shop",
      "storeName": "青山茶飲",
      "containerType": "cup",
      "soldCount": 10
    }
  ]
}
```

### GET `/government/daily/recovered`

每日回收彙總，讀 `daily_recovered_stats`。每一次成功掃碼回收都會把當天回收數加一。

Query params:

| Name | Required | Example |
|---|---|---|
| `from` | yes | `2026-05-09` |
| `to` | yes | `2026-05-09` |
| `storeId` | no | `2` |
| `containerType` | no | `cup` |

Response `200`:

```json
{
  "from": "2026-05-09",
  "to": "2026-05-09",
  "rows": [
    {
      "statDate": "2026-05-09",
      "storeId": 2,
      "storeCode": "bento-shop",
      "storeName": "晨光便當",
      "containerType": "cup",
      "recoveredCount": 6,
      "normalCount": 5,
      "expiredCount": 1,
      "abnormalCount": 1,
      "crossStoreCount": 2
    }
  ]
}
```

### GET `/government/invoices`

查發票批次列表。

Query params:

| Name | Required | Example |
|---|---|---|
| `from` | yes | `2026-05-08T00:00:00` |
| `to` | yes | `2026-05-10T23:59:59` |
| `storeId` | no | `1` |
| `status` | no | `active`, `partial_returned`, `returned` |

Response `200`:

```json
{
  "from": "2026-05-08T00:00:00",
  "to": "2026-05-10T23:59:59",
  "invoices": [
    {
      "loanId": 1,
      "invoiceCode": "INV-20260509-001",
      "qrValue": "INV-20260509-001|tea-shop",
      "storeId": 1,
      "storeCode": "tea-shop",
      "storeName": "青山茶飲",
      "status": "partial_returned",
      "containerType": "cup",
      "totalCupCount": 2,
      "returnedCount": 1,
      "remainingCupCount": 1,
      "issuedAt": "2026-05-09T12:05:32.062579",
      "dueAt": "2026-05-12T12:05:32.062579",
      "returnedAt": "2026-05-09T12:08:10.000000"
    }
  ]
}
```

### GET `/government/invoices/{loanId}`

單張發票批次詳情，包含掃描事件。

Response `200`:

```json
{
  "loanId": 1,
  "invoiceCode": "INV-20260509-001",
  "qrValue": "INV-20260509-001|tea-shop",
  "storeId": 1,
  "storeCode": "tea-shop",
  "storeName": "青山茶飲",
  "status": "partial_returned",
  "containerType": "cup",
  "totalCupCount": 2,
  "returnedCount": 1,
  "remainingCupCount": 1,
  "issuedAt": "2026-05-09T12:05:32.062579",
  "dueAt": "2026-05-12T12:05:32.062579",
  "returnedAt": "2026-05-09T12:08:10.000000",
  "returnedStoreId": 2,
  "returnedStoreCode": "bento-shop",
  "returnedStoreName": "晨光便當",
  "refundReason": "normal",
  "isExpired": false,
  "isAbnormal": false,
  "scanEvents": [
    {
      "id": 1,
      "result": "returned",
      "reason": null,
      "note": null,
      "storeId": 2,
      "storeCode": "bento-shop",
      "storeName": "晨光便當",
      "createdAt": "2026-05-09T12:08:10.000000"
    }
  ]
}
```

### GET `/government/anomalies`

異常掃描與需人工查核事件。

Query params:

| Name | Required | Example |
|---|---|---|
| `from` | yes | `2026-05-08T00:00:00` |
| `to` | yes | `2026-05-10T23:59:59` |
| `storeId` | no | `1` |
| `type` | no | `invalid_qr`, `duplicate_scan`, `expired`, `damaged`, `polluted`, `other` |

Response `200`:

```json
{
  "from": "2026-05-08T00:00:00",
  "to": "2026-05-10T23:59:59",
  "anomalies": [
    {
      "eventId": 3,
      "eventType": "return_scan",
      "result": "invalid_qr",
      "reason": "invalid_qr",
      "note": null,
      "storeId": 2,
      "storeCode": "bento-shop",
      "storeName": "晨光便當",
      "loanId": null,
      "invoiceCode": null,
      "qrValue": null,
      "totalCupCount": null,
      "returnedCount": null,
      "createdAt": "2026-05-09T12:09:00.000000"
    }
  ]
}
```

## 政府端 SQLite Views

政府端 web 主要走 `/government/...` API。若需要本地除錯或直接查 DB，也可讀 SQLite views。

### `v_gov_overview`

整體借出、回收、回收率、異常與押金統計。

```sql
SELECT * FROM v_gov_overview;
```

Columns:

| Column | Meaning |
|---|---|
| `loans_total` | 總借出數 |
| `returned_total` | 總回收數 |
| `recovery_rate` | 回收率 |
| `abnormal_total` | 逾期或異常回收數 |
| `deposit_total` | 押金總額 |
| `refund_total` | 已退押金總額 |

### `v_store_stats`

各店借出、回收、跨店回收與異常統計。

```sql
SELECT * FROM v_store_stats;
```

### `v_abnormal_events`

異常掃碼、逾期、破損、污染與重複掃碼清單。

```sql
SELECT * FROM v_abnormal_events ORDER BY created_at DESC;
```

### `v_daily_sold_stats`

每日賣出彙總，來自 `daily_sold_stats`，含店家代號與店名，方便政府端 web 直接做日報表。

```sql
SELECT * FROM v_daily_sold_stats ORDER BY stat_date, store_code;
```

### `v_daily_recovered_stats`

每日回收彙總，來自 `daily_recovered_stats`，含正常、逾期、異常、跨店回收分項。

```sql
SELECT * FROM v_daily_recovered_stats ORDER BY stat_date, store_code;
```

## Notes

- 時間以 `Asia/Taipei` 計算 3 天歸還期限，SQLite 內存 naive datetime。
- `qrValue` 使用 `發票代號|商家代號`；同一店家同一張發票只有一個 QR。
- DB 保存 `cup_count`、`returned_count` 與 SHA-256 `qr_token_hash`，不保存明文 `qrValue`。
- DB 另存 `daily_sold_stats` 與 `daily_recovered_stats`，每天每店每類型一列，用於政府端日統計。
- 第一版不串真實金流，只保存 `refund_ledgers` 作為後端退押帳本。
- 第一版不追蹤單一實體容器 ID。
