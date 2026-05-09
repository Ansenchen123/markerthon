from app.database import Base, engine
from app import models  # noqa: F401
from app.views import create_sqlite_views


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    create_sqlite_views(engine)
