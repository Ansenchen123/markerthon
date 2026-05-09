# 循環取還 Monorepo

這個 repo 先整理成三端結構：

```text
backend/   FastAPI + SQLite 後端
webapp/    商家端 Web App，待實作
web/       政府端 Web，待實作
```

從 repo 根目錄啟動後端：

```bash
python3 run.py --seed
```

或：

```bash
./run.py --seed
```

預設會啟動 `http://127.0.0.1:8000`，API 文件在 `http://127.0.0.1:8000/docs`。

後端開發也可以進入 `backend/` 手動啟動：

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

全端測試方法請看 [E2E_TESTING.md](E2E_TESTING.md)。之後要求「全端測試」時，應依此文件調用 subagents 扮演商家與政府端使用者。
