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
        if "cup_count" not in columns:
            conn.execute(text("ALTER TABLE loans ADD COLUMN cup_count INTEGER"))
            conn.execute(text("UPDATE loans SET cup_count = 1 WHERE cup_count IS NULL"))
        if "returned_count" not in columns:
            conn.execute(text("ALTER TABLE loans ADD COLUMN returned_count INTEGER"))
            conn.execute(
                text(
                    """
                    UPDATE loans
                    SET returned_count = CASE WHEN status = 'returned' THEN 1 ELSE 0 END
                    WHERE returned_count IS NULL
                    """
                )
            )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ix_loans_invoice_store_sequence
                ON loans (issued_store_id, invoice_code, invoice_sequence)
                """
            )
        )
