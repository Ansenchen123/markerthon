import hashlib

from app.database import Base, engine
from app import models  # noqa: F401
from app.views import create_sqlite_views
from sqlalchemy import inspect, text


def _qr_hash(invoice_code: str, store_code: str, category: str) -> str:
    qr_value = f"{invoice_code}|{store_code}|{category}"
    return hashlib.sha256(qr_value.encode("utf-8")).hexdigest()


def _legacy_qr_hash(invoice_code: str, store_code: str, category: str, loan_id: int) -> str:
    qr_value = f"{invoice_code}|{store_code}|{category}|legacy:{loan_id}"
    return hashlib.sha256(qr_value.encode("utf-8")).hexdigest()


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

        if "stores" in table_names:
            store_columns = {column["name"] for column in inspector.get_columns("stores")}
            if "region" not in store_columns:
                conn.execute(text("ALTER TABLE stores ADD COLUMN region VARCHAR(80)"))
                conn.execute(text("UPDATE stores SET region = '未設定' WHERE region IS NULL OR region = ''"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_stores_region ON stores (region)"))

    inspector = inspect(engine)
    if not inspector.has_table("loans"):
        return

    columns = {column["name"] for column in inspector.get_columns("loans")}
    with engine.begin() as conn:
        if "invoice_sequence" not in columns:
            conn.execute(text("ALTER TABLE loans ADD COLUMN invoice_sequence INTEGER"))
            conn.execute(text("UPDATE loans SET invoice_sequence = id WHERE invoice_sequence IS NULL"))
        if "item_count" not in columns:
            if "cup_count" in columns:
                conn.execute(text("ALTER TABLE loans RENAME COLUMN cup_count TO item_count"))
                columns.remove("cup_count")
                columns.add("item_count")
            else:
                conn.execute(text("ALTER TABLE loans ADD COLUMN item_count INTEGER"))
                conn.execute(text("UPDATE loans SET item_count = 1 WHERE item_count IS NULL"))
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
        if "remaining_count" not in columns:
            conn.execute(text("ALTER TABLE loans ADD COLUMN remaining_count INTEGER"))
            conn.execute(
                text(
                    """
                    UPDATE loans
                    SET remaining_count = MAX(item_count - returned_count, 0)
                    WHERE remaining_count IS NULL
                    """
                )
            )
        conn.execute(text("DROP INDEX IF EXISTS ix_loans_invoice_store_sequence"))
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ix_loans_invoice_store_type_sequence
                ON loans (issued_store_id, invoice_code, container_type, invoice_sequence)
                """
            )
        )
        rows = list(
            conn.execute(
                text(
                    """
                    SELECT
                        loans.id,
                        loans.invoice_code,
                        loans.invoice_sequence,
                        loans.container_type,
                        stores.code AS store_code
                    FROM loans
                    JOIN stores ON stores.id = loans.issued_store_id
                    """
                )
            ).mappings()
        )
        qr_hash_groups = {}
        for row in rows:
            target_hash = _qr_hash(row["invoice_code"], row["store_code"], row["container_type"])
            qr_hash_groups.setdefault(target_hash, []).append(row)

        for target_hash, group in qr_hash_groups.items():
            primary = min(group, key=lambda row: (row["invoice_sequence"] != 1, row["id"]))
            for row in group:
                if row["id"] == primary["id"]:
                    continue
                conn.execute(
                    text("UPDATE loans SET qr_token_hash = :qr_token_hash WHERE id = :loan_id"),
                    {
                        "loan_id": row["id"],
                        "qr_token_hash": _legacy_qr_hash(
                            row["invoice_code"],
                            row["store_code"],
                            row["container_type"],
                            row["id"],
                        ),
                    },
                )
            conn.execute(
                text("UPDATE loans SET qr_token_hash = :qr_token_hash WHERE id = :loan_id"),
                {"loan_id": primary["id"], "qr_token_hash": target_hash},
            )
