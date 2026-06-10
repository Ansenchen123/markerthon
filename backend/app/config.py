import os
from dataclasses import dataclass


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"{name} environment variable is required")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/reusable_container.db")
    daily_report_dir: str = os.getenv("DAILY_REPORT_DIR", "./data/daily_reports")
    jwt_secret: str = _required_env("JWT_SECRET")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
    auto_init_db: bool = os.getenv("AUTO_INIT_DB", "true").lower() == "true"


settings = Settings()
