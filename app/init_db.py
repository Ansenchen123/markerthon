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
    table_names = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "government_users" not in table_names:
            conn.execute(
                text(
                    """
                    CREATE TABLE government_users (
                        id INTEGER NOT NULL,
                        username VARCHAR(80) NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        created_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        UNIQUE (username)
                    )
                    """
                )
            )
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_government_users_username ON government_users (username)"))
            table_names.add("government_users")
            inspector = inspect(engine)

        if "merchant_users" in table_names:
            merchant_columns = {column["name"] for column in inspector.get_columns("merchant_users")}
            if "user_email" not in merchant_columns:
                conn.execute(text("ALTER TABLE merchant_users ADD COLUMN user_email VARCHAR(255)"))
                conn.execute(
                    text(
                        """
                        UPDATE merchant_users
                        SET user_email = CASE
                            WHEN username LIKE '%@%' THEN lower(username)
                            ELSE lower(username || '@example.local')
                        END
                        WHERE user_email IS NULL
                        """
                    )
                )
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_merchant_users_user_email ON merchant_users (user_email)"))

        if "government_users" in table_names:
            government_columns = {column["name"] for column in inspector.get_columns("government_users")}
            if "user_email" not in government_columns:
                conn.execute(text("ALTER TABLE government_users ADD COLUMN user_email VARCHAR(255)"))
                conn.execute(
                    text(
                        """
                        UPDATE government_users
                        SET user_email = CASE
                            WHEN username LIKE '%@%' THEN lower(username)
                            ELSE lower(username || '@example.local')
                        END
                        WHERE user_email IS NULL
                        """
                    )
                )
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_government_users_user_email ON government_users (user_email)"))

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
