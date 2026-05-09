from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.init_db import init_db
from app.routers.auth import router as auth_router
from app.routers.government import router as government_router
from app.routers.merchant import router as merchant_router
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_init_db:
        init_db()
    yield


app = FastAPI(
    title="循環取還 Backend MVP",
    version="0.1.0",
    description="Merchant-facing APIs for reusable cup and meal-box deposit returns.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(merchant_router)
app.include_router(government_router)
