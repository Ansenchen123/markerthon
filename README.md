# 循環取還 Monorepo

這個 repo 先整理成三端結構：

```text
backend/   FastAPI + SQLite 後端
webapp/    商家端 Web App，待實作
web/       政府端 Web，待實作
```

後端開發請進入 `backend/`：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
python -m app.demo_data
uvicorn app.main:app --reload
```

API 與後端細節請看 [backend/API_USAGE.md](backend/API_USAGE.md) 與 [backend/README.md](backend/README.md)。
