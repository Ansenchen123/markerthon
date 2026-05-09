# 全端測試作業規範

當使用者要求「全端測試」、「完整流程測試」、「端到端測試」或語意相近的任務時，必須使用本文件的角色式黑箱測試流程。

## 核心原則

- 必須調用 subagents，讓不同 subagent 扮演不同角色使用者。
- subagents 應以不知情黑箱使用者角度操作，只能使用 HTTP API、文件與 OpenAPI，不直接查 DB、不修改檔案。
- 主 agent 負責測試環境、監控資料流、DB/CSV/API 對帳、彙整結果與修正低風險文件落差。
- 測試應使用隔離資料庫與隔離 CSV 目錄，避免污染 demo 或開發資料。

## 建議測試環境

從 `backend/` 啟動一個隔離服務，例如：

```bash
cd backend
rm -rf data/agent_e2e.db data/agent_e2e_reports
DATABASE_URL=sqlite:///./data/agent_e2e.db \
DAILY_REPORT_DIR=./data/agent_e2e_reports \
JWT_SECRET=agent-e2e-secret \
../.venv/bin/python -m app.seed

DATABASE_URL=sqlite:///./data/agent_e2e.db \
DAILY_REPORT_DIR=./data/agent_e2e_reports \
JWT_SECRET=agent-e2e-secret \
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8013
```

啟動後先確認：

```bash
curl -s http://127.0.0.1:8013/health
```

## Subagent 角色

### 商家 subagent

任務範圍：

- 登入 demo 商家帳號。
- 查詢商家 sold/recovered baseline stats。
- 建立至少兩張 QR：
  - 同一發票、同一 `category` 重複建立，確認 `count` 會追加到同一 QR。
  - 同一發票、不同 `category` 建立，確認會產生不同 QR。
- 掃描回收至少一筆 QR。
- 嘗試重複掃描與無效 QR，確認錯誤處理。
- 查詢商家 sold/recovered stats，確認 `storeId` 必填且 scope 正確。

商家 subagent 最終回報：

- 呼叫過的 endpoint。
- HTTP status。
- 重要 request/response 欄位。
- stats 是否符合操作結果。
- 文件或前端串接可能卡住的地方。

### 政府 subagent

任務範圍：

- 登入 demo 政府帳號。
- 查詢 `monthly-usage`、`enterprise-counts`、`region-distribution`、`top-cup-stores`、`stores/{storeId}`。
- 使用覆蓋當月的 `year`、`month`。
- 測試 `limit` 與不存在的 `storeId`。
- 確認舊政府查詢 API 已移除：`/government/overview`、`/government/stores`、`/government/daily/*`、`/government/invoices*`、`/government/anomalies` 都應回 `404`。
- 等商家 subagent 寫入資料後重查一次，確認資料有反映。

政府 subagent 最終回報：

- 呼叫過的 endpoint。
- HTTP status。
- 重要數字與欄位。
- filter 是否符合文件。
- 文件或政府端前端可能卡住的地方。

## 主 Agent 監控項目

主 agent 需同步監控：

- server log：確認實際 request path、query、status code。
- DB：
  - `loans.item_count`
  - `loans.returned_count`
  - `loans.remaining_count`
  - `loans.status`
  - `refund_ledgers`
  - `scan_events`
- CSV：
  - `daily_report_YYYY-MM-DD.csv`
  - `eventType=sold`
  - `eventType=recovered`
  - `category`
  - `count`
  - `totalCount`
  - `returnedCount`
  - `remainingCount`
- API 聚合結果：
  - 商家 stats。
  - 政府 web monthly usage、enterprise counts、region distribution、top cup stores、store status。

## 必查不變條件

- DB 借出總數 `sum(item_count)` 等於 CSV sold `sum(count)`。
- DB 回收總數 `sum(returned_count)` 等於 CSV recovered `sum(count)`。
- DB 未歸還總數 `sum(remaining_count)` 等於 `sum(item_count - returned_count)`。
- `remainingCount = totalCount - returnedCount`，且成功掃描一次時 DB `remaining_count` 要少 1。
- 同一商家、同一發票、同一 `category` 會共用同一 QR 並追加數量。
- 同一商家、同一發票、不同 `category` 會分成不同 QR。
- 掃描一次只回收一個容器。
- 已全數回收的 QR 再掃描應回 `409`，並寫入 `scan_events.result=duplicate_scan`。
- 無效 QR 應回 `404`，並寫入 `scan_events.result=invalid_qr`。
- 商家 stats 的 `storeId` 必須和登入 token 所屬店家一致，否則回 `403`。
- 政府端 web API 應只保留 `/government/web/...` 查詢路徑，不可讓舊 `/government/overview`、`/government/stores`、`/government/daily/*`、`/government/invoices*`、`/government/anomalies` 混入文件或 OpenAPI。
- 公開 API 與文件不得回到 `cup_count`、`cupCount`、`containerType` 等舊命名。

## 結果報告格式

回報時應包含：

- 測試環境：base URL、隔離 DB、隔離 CSV 目錄。
- 商家 subagent 摘要。
- 政府 subagent 摘要。
- 主 agent 監控到的 DB/CSV/API 對帳結果。
- 是否符合預期。
- 發現的 bug、文件落差或前端風險。
- 若有修正，列出修正檔案、測試指令與 commit。

## 修正原則

- 若發現低風險文件落差或 OpenAPI metadata 漏列錯誤狀態，可直接修正並跑測試。
- 若發現會改變 API contract、資料模型或商業規則的問題，先回報並詢問使用者再改。
- 測試完成後關閉本地服務，不要留下必要以外的背景程序。
