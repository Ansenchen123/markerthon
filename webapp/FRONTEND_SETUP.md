# Frontend Setup

此 repo 是純前端 Web App 專案。後端不放在此專案內，前端只透過 HTTP API 串接。

## Stack

- Vite
- React
- TypeScript

## Commands

```bash
npm install
npm run dev
npm run build
npm run preview
```

## API Boundary

複製 `.env.example` 成 `.env.local`，並設定後端 API 網址：

```bash
VITE_API_BASE_URL=https://your-api.example.com
```

API 呼叫集中放在 `src/api`，避免前端頁面直接散落後端網址或 request 細節。
