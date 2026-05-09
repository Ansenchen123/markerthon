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
python -m app.demo_data
uvicorn app.main:app --reload
```

Demo accounts:

| Store | Region | User Email | Password |
|---|---|---|---|
| 青山茶飲 | 台北市大安區 | `tea.owner@example.com` | `password123` |
| 青山茶飲 | 台北市大安區 | `tea.staff@example.com` | `password123` |
| 晨光便當 | 台北市中山區 | `bento.owner@example.com` | `password123` |
| 巷口咖啡 | 新北市板橋區 | `cafe.owner@example.com` | `password123` |
| 政府端管理 | - | `gov.admin@example.com` | `password123` |

### 產生五天 Demo CSV

```bash
python -m app.demo_data
```

這個指令會：

| Step | What it does |
|---|---|
| 1 | 建立 demo 商家與政府帳號 |
| 2 | 清除舊的 `DEMO-` 發票測試資料，避免重跑後數量膨脹 |
| 3 | 用正常 API 登入、產生 QR、掃碼回收 |
| 4 | 只把後端時間暫時改成過去五天，產生 `daily_report_YYYY-MM-DD.csv` |
| 5 | 呼叫政府端 web API 與商家統計 API 驗證整個流程 |

預設會產生過去五天的 CSV，例如：

```text
data/daily_reports/daily_report_2026-05-05.csv
data/daily_reports/daily_report_2026-05-06.csv
data/daily_reports/daily_report_2026-05-07.csv
data/daily_reports/daily_report_2026-05-08.csv
data/daily_reports/daily_report_2026-05-09.csv
```

## Auth

除了登入以外，商家 API 都要帶 JWT：

```http
Authorization: Bearer <accessToken>
```

### POST `/auth/register`

商家註冊，會同時建立店家資料與商家帳號。`storeCode` 由後端自動產生，前端不需要傳。若 `storeName` 已存在，新的 `userEmail` 會綁到同一家店；`userEmail` 全系統唯一。註冊成功後直接回傳 JWT。
建議欄位使用 `userEmail`；後端也接受 `useremail`、`email`、`username` 作為輸入別名。

Request:

```json
{
  "userEmail": "new.merchant@example.com",
  "password": "password123",
  "storeName": "新店家",
  "region": "台北市信義區"
}
```

`region` 是店家所在地區，供政府端企業地區分布圖使用；若未傳，後端會填 `未設定`。

Response `201`:

```json
{
  "accessToken": "<jwt>",
  "tokenType": "bearer",
  "store": {
    "id": 4,
    "code": "store-a1b2c3d4",
    "name": "新店家",
    "region": "台北市信義區"
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
建議欄位使用 `userEmail`；為了相容前端大小寫與舊版欄位，後端也接受 `useremail`、`email`、`username` 作為輸入別名。

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
    "name": "青山茶飲",
    "region": "台北市大安區"
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

店家賣出循環容器時呼叫。店家輸入發票號碼、分類標籤與數量，後端會依「商家 + 發票 + 分類標籤」找到同一筆發票批次紀錄並累加 `count`。同一張發票在同一分類標籤下只會有一個 `qrValue`；前端只需要把這個 `qrValue` 生成一張 QR Code 圖。

QR 代表本次借出憑證，不代表實體容器 ID。容器本身不綁定識別碼。

`qrValue` 格式：

```text
<invoiceCode>|<storeCode>|<category>
```

例如同一家店同一張發票有兩杯飲料，只會產生：

```text
INV-20260509-001|tea-shop|cup
```

數量差異由後端 `count` / `totalCount` / `returnedCount` / `remainingCount` 記錄，不在 QR 裡區分單一容器。若同一張發票同時包含杯子與餐盒，因分類標籤不同，會分別產生 `...|cup` 與 `...|meal_box` 兩個 QR。

Request:

```json
{
  "invoiceCode": "INV-20260509-001",
  "category": "cup",
  "count": 2
}
```

`category` 可為 `cup` 或 `meal_box`。同一店同一發票同一分類標籤會累加同一筆紀錄；不同分類標籤會建立不同 QR。`count` 最小為 `1`，最大為 `100`。押金由後端內部帳本處理，不在商家 API 回傳。

Response `201`:

```json
{
  "loanId": 1,
  "qrValue": "INV-20260509-001|tea-shop|cup",
  "invoiceCode": "INV-20260509-001",
  "storeCode": "tea-shop",
  "category": "cup",
  "addedCount": 2,
  "totalCount": 2,
  "returnedCount": 0,
  "remainingCount": 2,
  "issuedAt": "2026-05-09T12:05:32.062579",
  "dueAt": "2026-05-12T12:05:32.062579"
}
```

DB changes:

| Table | Change |
|---|---|
| `loans` | 同店同發票同分類標籤不存在時新增一筆；已存在時更新同一筆 `item_count += count`，保存分類欄位與 `qr_token_hash`，不保存明文 `qrValue` |

### 2. POST `/merchant/returns/scan`

店家掃描 QR 回收容器時呼叫。掃描一次代表回收 1 個容器，前端只需要送出 `qrValue`，不需要輸入數量、容器狀態或備註。後端會自行判斷 QR 是否存在、是否重複掃描、是否逾期，並累加 `returnedCount`，直到 `remainingCount` 為 0 才把狀態標記為 `returned`。

Request:

```json
{
  "qrValue": "INV-20260509-001|tea-shop|cup"
}
```

Response `200` for normal in-time return:

```json
{
  "accepted": true,
  "loanId": 1,
  "status": "partial_returned",
  "category": "cup",
  "invoiceCode": "INV-20260509-001",
  "issuedStoreId": 1,
  "returnedStoreId": 1,
  "count": 1,
  "totalCount": 2,
  "returnedCount": 1,
  "remainingCount": 1,
  "refundReason": "normal",
  "isExpired": false,
  "isAbnormal": false,
  "dueAt": "2026-05-12T12:05:32.062579",
  "returnedAt": "2026-05-09T12:05:32.066739"
}
```

`status` 是這張 QR/發票容器批次的目前狀態，不是單次掃描事件結果：

| Value | Meaning |
|---|---|
| `active` | 還沒有任何回收 |
| `partial_returned` | 已回收一部分，但 `remainingCount` 還大於 0 |
| `returned` | 這張 QR 的數量已全數回收 |

單次掃描是否正常或逾期請看 `refundReason`、`isExpired`、`isAbnormal`。目前商家前端不送容器狀態，所以 `isAbnormal` 只保留給後續後端自動判定或歷史資料；內部稽核用的單次掃描結果會寫進 `scan_events.result`，例如 `returned`、`returned_no_refund`、`duplicate_scan`、`invalid_qr`。

Response `200` for expired return:

```json
{
  "accepted": true,
  "loanId": 1,
  "status": "partial_returned",
  "category": "cup",
  "invoiceCode": "INV-20260509-001",
  "issuedStoreId": 1,
  "returnedStoreId": 2,
  "count": 1,
  "totalCount": 2,
  "returnedCount": 1,
  "remainingCount": 1,
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

查詢指定商家在日期區間內每天賣出多少循環容器。`storeId` 必須等於登入商家 JWT 所屬店家；若傳入其他商家會回 `403`。商家端不提供分類 filter；後端會一次回傳全部分類，並在每天的 row 裡用 `categoryCounts` 列出各分類數量。日期區間含頭含尾，查幾天就回傳幾筆；沒有資料的日期會回 0。

Query params:

| Name | Required | Example |
|---|---|---|
| `storeId` | yes | `1` |
| `from` | yes | `2026-05-08` |
| `to` | yes | `2026-05-10` |

Example:

```http
GET /merchant/stats/sold?storeId=1&from=2026-05-08&to=2026-05-10
Authorization: Bearer <accessToken>
```

Response `200`:

```json
{
  "storeId": 1,
  "from": "2026-05-08",
  "to": "2026-05-10",
  "rows": [
    {
      "statDate": "2026-05-08",
      "totalCount": 0,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 0
        },
        {
          "category": "meal_box",
          "count": 0
        }
      ]
    },
    {
      "statDate": "2026-05-09",
      "totalCount": 1,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 1
        },
        {
          "category": "meal_box",
          "count": 0
        }
      ]
    },
    {
      "statDate": "2026-05-10",
      "totalCount": 0,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 0
        },
        {
          "category": "meal_box",
          "count": 0
        }
      ]
    }
  ]
}
```

CSV read:

| Source | Filter |
|---|---|
| `daily_report_YYYY-MM-DD.csv` | `eventType = sold`、`storeId = query storeId`、`occurredAt` date between `from` and `to` |

### 4. GET `/merchant/stats/recovered`

查詢指定商家在日期區間內每天回收多少循環容器。`storeId` 必須等於登入商家 JWT 所屬店家；若傳入其他商家會回 `403`。商家端不提供分類 filter；後端會一次回傳全部分類，並在每天的 row 裡列出總數、`categoryCounts` 與回收狀態分項。日期區間含頭含尾，查幾天就回傳幾筆；沒有資料的日期會回 0。

Query params:

| Name | Required | Example |
|---|---|---|
| `storeId` | yes | `1` |
| `from` | yes | `2026-05-08` |
| `to` | yes | `2026-05-10` |

Example:

```http
GET /merchant/stats/recovered?storeId=1&from=2026-05-08&to=2026-05-10
Authorization: Bearer <accessToken>
```

Response `200`:

```json
{
  "storeId": 1,
  "from": "2026-05-08",
  "to": "2026-05-10",
  "rows": [
    {
      "statDate": "2026-05-08",
      "totalCount": 0,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 0
        },
        {
          "category": "meal_box",
          "count": 0
        }
      ],
      "normalCount": 0,
      "expiredCount": 0,
      "abnormalCount": 0,
      "crossStoreCount": 0
    },
    {
      "statDate": "2026-05-09",
      "totalCount": 1,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 1
        },
        {
          "category": "meal_box",
          "count": 0
        }
      ],
      "normalCount": 1,
      "expiredCount": 0,
      "abnormalCount": 0,
      "crossStoreCount": 1
    },
    {
      "statDate": "2026-05-10",
      "totalCount": 0,
      "categoryCounts": [
        {
          "category": "cup",
          "count": 0
        },
        {
          "category": "meal_box",
          "count": 0
        }
      ],
      "normalCount": 0,
      "expiredCount": 0,
      "abnormalCount": 0,
      "crossStoreCount": 0
    }
  ]
}
```

CSV read:

| Source | Filter |
|---|---|
| `daily_report_YYYY-MM-DD.csv` | `eventType = recovered`、`storeId = query storeId`、`occurredAt` date between `from` and `to` |

## cURL 全流程範例

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"userEmail":"tea.owner@example.com","password":"password123"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')

QR_VALUE=$(curl -s -X POST http://127.0.0.1:8000/merchant/qr-codes \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"invoiceCode":"INV-DEMO-001","category":"cup","count":2}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["qrValue"])')

curl -s -X POST http://127.0.0.1:8000/merchant/returns/scan \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"qrValue\":\"$QR_VALUE\"}"

curl -s "http://127.0.0.1:8000/merchant/stats/sold?storeId=1&from=2026-05-08&to=2026-05-10" \
  -H "Authorization: Bearer $TOKEN"

curl -s "http://127.0.0.1:8000/merchant/stats/recovered?storeId=1&from=2026-05-08&to=2026-05-10" \
  -H "Authorization: Bearer $TOKEN"
```

## 政府端 Web API

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

目前政府 web 應串接以下五個新版查詢接口；若 `year`、`month` 省略，後端會使用目前台北時間的年月。

### GET `/government/web/monthly-usage`

本月使用情況。

Query params:

| Name | Required | Example |
|---|---|---|
| `year` | no | `2026` |
| `month` | no | `5` |

Response `200`:

```json
{
  "month": "2026-05",
  "from": "2026-05-01T00:00:00",
  "to": "2026-05-31T23:59:59.999999",
  "issuedCount": 7,
  "returnedCount": 3,
  "remainingCount": 4,
  "recoveryRate": 0.4286,
  "activeInvoiceCount": 0,
  "partialReturnedInvoiceCount": 2,
  "returnedInvoiceCount": 1,
  "overdueCount": 0,
  "abnormalCount": 0,
  "daily": [
    {
      "statDate": "2026-05-09",
      "issuedCount": 7,
      "returnedCount": 3
    }
  ]
}
```

### GET `/government/web/enterprise-counts`

本月企業加入數量與目前企業總數。

Query params: optional `year`, `month`

Response `200`:

```json
{
  "month": "2026-05",
  "from": "2026-05-01T00:00:00",
  "to": "2026-05-31T23:59:59.999999",
  "monthJoinedCount": 3,
  "totalEnterpriseCount": 3
}
```

### GET `/government/web/region-distribution`

企業所在地區數量分布圖資料。

Response `200`:

```json
{
  "totalEnterpriseCount": 3,
  "regions": [
    {
      "region": "台北市大安區",
      "enterpriseCount": 1
    },
    {
      "region": "台北市中山區",
      "enterpriseCount": 1
    }
  ]
}
```

### GET `/government/web/top-cup-stores`

本月環保杯使用 Top 排名。只統計 `category = cup`。

Query params:

| Name | Required | Example |
|---|---|---|
| `year` | no | `2026` |
| `month` | no | `5` |
| `limit` | no | `10` |

Response `200`:

```json
{
  "month": "2026-05",
  "from": "2026-05-01T00:00:00",
  "to": "2026-05-31T23:59:59.999999",
  "category": "cup",
  "rankings": [
    {
      "rank": 1,
      "storeId": 1,
      "storeCode": "tea-shop",
      "storeName": "青山茶飲",
      "region": "台北市大安區",
      "issuedCount": 4,
      "returnedCount": 1,
      "remainingCount": 3,
      "recoveryRate": 0.25
    }
  ]
}
```

### GET `/government/web/stores/{storeId}`

特定店家狀況查詢。

Query params: optional `year`, `month`

Response `200`:

```json
{
  "month": "2026-05",
  "from": "2026-05-01T00:00:00",
  "to": "2026-05-31T23:59:59.999999",
  "store": {
    "id": 1,
    "code": "tea-shop",
    "name": "青山茶飲",
    "region": "台北市大安區",
    "createdAt": "2026-05-09T12:00:00"
  },
  "issuedCount": 6,
  "returnedCount": 2,
  "recoveredCount": 2,
  "remainingCount": 4,
  "recoveryRate": 0.3333,
  "cupIssuedCount": 4,
  "cupReturnedCount": 1,
  "mealBoxIssuedCount": 2,
  "mealBoxReturnedCount": 1,
  "overdueCount": 0,
  "abnormalCount": 0,
  "crossStoreRecoveredCount": 0,
  "lastActivityAt": "2026-05-09T12:10:00"
}
```

Failure:

| Status | Meaning |
|---:|---|
| 404 | 店家不存在 |

## 政府端 SQLite Views

政府端 web 主要走 `/government/web/...` API。若需要本地除錯或直接查 DB，也可讀 SQLite views。

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

## 每日 CSV 報表

每日報表預設輸出到 `data/daily_reports/`，也可以用環境變數 `DAILY_REPORT_DIR` 改路徑。檔名格式：

```text
daily_report_YYYY-MM-DD.csv
```

同一天的賣出與回收都寫在同一個 CSV，透過 `eventType` 區分：

| eventType | 寫入時機 |
|---|---|
| `sold` | `POST /merchant/qr-codes` 成功後追加一列 |
| `recovered` | `POST /merchant/returns/scan` 成功回收一杯後追加一列 |

常用欄位：

| Column | Meaning |
|---|---|
| `eventType` | `sold` 或 `recovered` |
| `occurredAt` | 事件時間 |
| `loanId` | 發票批次 ID |
| `invoiceCode` | 發票號碼 |
| `qrValue` | QR 文字值 |
| `storeId`, `storeCode`, `storeName` | 本事件所屬店家；賣出為出餐店，回收為掃碼店 |
| `issuedStore*` | 原始出餐店 |
| `returnedStore*` | 回收店，只有回收事件有值 |
| `category` | 分類標籤，例如 `cup` 或 `meal_box` |
| `count` | 本次事件數量；賣出可能大於 1，回收固定為 1 |
| `totalCount` | 該 QR/發票目前累計數量 |
| `returnedCount` | 該 QR/發票目前已回收數量 |
| `remainingCount` | 該 QR/發票目前未回收數量 |
| `condition`, `result`, `reason` | 後端判定的回收狀態與原因 |
| `isExpired`, `isAbnormal`, `isCrossStore` | 回收統計旗標 |

## Notes

- 時間以 `Asia/Taipei` 計算 3 天歸還期限，SQLite 內存 naive datetime。
- `qrValue` 使用 `發票代號|商家代號|分類標籤`；同一店家同一張發票同一分類標籤只有一個 QR。
- DB 保存 `item_count`、`returned_count` 與 SHA-256 `qr_token_hash`，不保存明文 `qrValue`。
- 每日統計不再用 DB table；後端以每日 CSV append log 控制資料量，商家統計 API 會讀 CSV 聚合。政府端 web API 讀目前資料庫彙總本月使用情況與店家狀態。商家統計 API 不提供分類 filter，會在每日 row 中回傳 `categoryCounts`。
- 第一版不串真實金流，只保存 `refund_ledgers` 作為後端退押帳本。
- 第一版不追蹤單一實體容器 ID。
