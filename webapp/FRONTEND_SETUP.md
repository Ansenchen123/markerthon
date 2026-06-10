# Merchant Frontend Setup

## Stack

- Vite
- React
- TypeScript

## Commands

```powershell
npm install
npm run dev
npm run build
npm run preview
```

## API Boundary

The merchant frontend reads `VITE_API_BASE_URL` and defaults to `http://127.0.0.1:8000`.

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
```

HTTP calls are isolated in `webapp/src/api/client.ts`. The merchant frontend uses `/auth` and `/merchant` endpoints only.
