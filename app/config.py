import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/reusable_container.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-change-me")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
    auto_init_db: bool = os.getenv("AUTO_INIT_DB", "true").lower() == "true"


settings = Settings()
