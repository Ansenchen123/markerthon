from app.database import Base, engine
from app import models  # noqa: F401
from app.views import create_sqlite_views
from sqlalchemy import inspect, text


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_compatibility()
    create_sqlite_views(engine)


def ensure_sqlite_compatibility() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if not inspector.has_table("loans"):
        return

    columns = {column["name"] for column in inspector.get_columns("loans")}
    with engine.begin() as conn:
        if "invoice_sequence" not in columns:
            conn.execute(text("ALTER TABLE loans ADD COLUMN invoice_sequence INTEGER"))
            conn.execute(text("UPDATE loans SET invoice_sequence = id WHERE invoice_sequence IS NULL"))
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ix_loans_invoice_store_sequence
                ON loans (issued_store_id, invoice_code, invoice_sequence)
                """
            )
        )
