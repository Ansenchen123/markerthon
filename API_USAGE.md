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

| Store | Username | Password |
|---|---|---|
| 青山茶飲 | `tea_owner` | `password123` |
| 晨光便當 | `bento_owner` | `password123` |
| 巷口咖啡 | `cafe_owner` | `password123` |

## Auth

除了登入以外，商家 API 都要帶 JWT：

```http
Authorization: Bearer <accessToken>
```

### POST `/auth/login`

商家登入，成功後回傳 JWT 與商家資料。

Request:

```json
{
  "username": "tea_owner",
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
| 401 | 帳號或密碼錯誤 |

## 四個主要商家 API

### 1. POST `/merchant/qr-codes`

店家賣出循環杯或餐盒時呼叫。後端建立一次借出紀錄，回傳 `qrValue`；前端負責把 `qrValue` 生成 QR Code 圖。

QR 代表本次借出憑證，不代表實體容器 ID。容器本身不綁定識別碼。

`qrValue` 格式：

```text
<invoiceCode>|<storeCode>|<invoiceSequence>
```

例如同一家店同一張發票有兩杯飲料，會產生：

```text
INV-20260509-001|tea-shop|1
INV-20260509-001|tea-shop|2
```

序號 `invoiceSequence` 會在同一店家、同一張發票內遞增；換另一張發票會重新從 1 開始。

Request:

```json
{
  "containerType": "cup",
  "invoiceCode": "INV-20260509-001",
  "note": "optional note"
}
```

`containerType`:

| Value | Deposit |
|---|---:|
| `cup` | 20 |
| `meal_box` | 50 |

Response `201`:

```json
{
  "loanId": 1,
  "qrValue": "INV-20260509-001|tea-shop|1",
  "containerType": "cup",
  "invoiceCode": "INV-20260509-001",
  "invoiceSequence": 1,
  "depositAmount": 20,
  "issuedAt": "2026-05-09T12:05:32.062579",
  "dueAt": "2026-05-12T12:05:32.062579"
}
```

DB changes:

| Table | Change |
|---|---|
| `loans` | 新增一筆 `status='active'` 的借出紀錄，保存 `invoice_sequence` 與 `qr_token_hash`，不保存明文 `qrValue` |

### 2. POST `/merchant/returns/scan`

店家掃描 QR 回收容器時呼叫。掃描成功後，該 QR 立即失效，避免重複退押。

Request:

```json
{
  "qrValue": "INV-20260509-001|tea-shop|1",
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
  "invoiceSequence": 1,
  "issuedStoreId": 1,
  "returnedStoreId": 1,
  "depositAmount": 20,
  "refundAmount": 20,
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
  "invoiceSequence": 1,
  "issuedStoreId": 1,
  "returnedStoreId": 2,
  "depositAmount": 20,
  "refundAmount": 0,
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
| `loans` | 更新為 `status='returned'`，寫入 `returned_store_id`、`returned_at`、`return_condition`、異常備註 |
| `refund_ledgers` | 新增退押帳本；正常未逾期為全額，逾期或異常為 0 |
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
  "mealBoxCount": 0,
  "depositTotal": 20
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
  "crossStoreCount": 0,
  "refundTotal": 20
}
```

DB read:

| Table | Filter |
|---|---|
| `loans` | `returned_store_id = current_store_id` and `returned_at` between `from` and `to` |
| `refund_ledgers` | 加總同一批回收紀錄的 `refund_amount` |

## cURL 全流程範例

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"tea_owner","password":"password123"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')

QR_VALUE=$(curl -s -X POST http://127.0.0.1:8000/merchant/qr-codes \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"containerType":"cup","invoiceCode":"INV-DEMO-001"}' \
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

## 政府端 Web 直接讀取的 SQLite Views

政府端 web 第一版不走後端 API，可直接讀 SQLite views。

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

## Notes

- 時間以 `Asia/Taipei` 計算 3 天歸還期限，SQLite 內存 naive datetime。
- `qrValue` 使用 `發票代號|商家代號|序號`；序號在同一店家同一張發票內遞增，換發票重置為 1。
- DB 保存 `invoice_sequence` 與 SHA-256 `qr_token_hash`，不保存明文 `qrValue`。
- 第一版不串真實金流，只保存 `refund_ledgers` 作為後端退押帳本。
- 第一版不追蹤單一實體容器 ID。
