# 政府 Web API Usage

Base URL:

```text
http://127.0.0.1:8000
```

政府 web 只串 `/government/...` 路徑；商家 web app 使用 `/auth` 與 `/merchant/...`，兩邊 token 不能混用。

## Auth Header

除登入與註冊外，所有政府 web 查詢 API 都要帶：

```http
Authorization: Bearer <governmentAccessToken>
```

## POST `/government/auth/login`

政府端登入。

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

常見錯誤：

| Status | Meaning |
|---:|---|
| 401 | 帳號或密碼錯誤 |
| 422 | Email 格式錯誤或缺少欄位 |

## POST `/government/auth/register`

政府端註冊，成功後直接回傳 JWT。

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

常見錯誤：

| Status | Meaning |
|---:|---|
| 409 | Email 已存在 |
| 422 | Email 格式錯誤或密碼少於 8 碼 |

## GET `/government/web/monthly-usage`

本月使用情況。若不傳 `year`、`month`，後端使用目前台北時間的年月。

Query:

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

## GET `/government/web/enterprise-counts`

本月企業加入數量與企業總數。

Query:

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
  "monthJoinedCount": 3,
  "totalEnterpriseCount": 3
}
```

## GET `/government/web/region-distribution`

企業所在地區數量分布圖資料。地區來自商家註冊的 `region` 欄位。

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

## GET `/government/web/top-cup-stores`

本月環保杯使用 Top 排名，只統計 `category = cup`。

Query:

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

## GET `/government/web/stores/{storeId}`

特定店家狀況查詢。

Path:

| Name | Example |
|---|---|
| `storeId` | `1` |

Query:

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

常見錯誤：

| Status | Meaning |
|---:|---|
| 404 | 店家不存在 |

## Frontend Notes

- `year`、`month` 建議由前端月份選擇器提供；省略時會查目前月份。
- `recoveryRate` 是 0 到 1 的小數，前端若要顯示百分比請自行乘以 100。
- `issuedCount` 是借出數，`returnedCount` 是這批借出已回收數，`recoveredCount` 是該店實際掃回的數量。
- API 不回傳押金金額；金額只保留在後端帳本。
