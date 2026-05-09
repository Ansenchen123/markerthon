"""include container type in qr values

Revision ID: 0008_include_container_type_in_qr
Revises: 0007_drop_daily_stats_tables
Create Date: 2026-05-09
"""

import hashlib

from alembic import op
import sqlalchemy as sa


revision = "0008_include_container_type_in_qr"
down_revision = "0007_drop_daily_stats_tables"
branch_labels = None
depends_on = None


def _qr_hash(invoice_code: str, store_code: str, container_type: str) -> str:
    qr_value = f"{invoice_code}|{store_code}|{container_type}"
    return hashlib.sha256(qr_value.encode("utf-8")).hexdigest()


def _legacy_qr_hash(invoice_code: str, store_code: str, container_type: str, loan_id: int) -> str:
    qr_value = f"{invoice_code}|{store_code}|{container_type}|legacy:{loan_id}"
    return hashlib.sha256(qr_value.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_loans_invoice_store_sequence")
    op.create_index(
        "ix_loans_invoice_store_type_sequence",
        "loans",
        ["issued_store_id", "invoice_code", "container_type", "invoice_sequence"],
        unique=True,
    )

    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
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
            bind.execute(
                sa.text("UPDATE loans SET qr_token_hash = :qr_token_hash WHERE id = :loan_id"),
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
        bind.execute(
            sa.text("UPDATE loans SET qr_token_hash = :qr_token_hash WHERE id = :loan_id"),
            {"loan_id": primary["id"], "qr_token_hash": target_hash},
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT loans.id, loans.invoice_code, stores.code AS store_code
            FROM loans
            JOIN stores ON stores.id = loans.issued_store_id
            """
        )
    ).mappings()
    for row in rows:
        old_qr_value = f"{row['invoice_code']}|{row['store_code']}"
        bind.execute(
            sa.text("UPDATE loans SET qr_token_hash = :qr_token_hash WHERE id = :loan_id"),
            {
                "loan_id": row["id"],
                "qr_token_hash": hashlib.sha256(old_qr_value.encode("utf-8")).hexdigest(),
            },
        )

    op.execute("DROP INDEX IF EXISTS ix_loans_invoice_store_type_sequence")
    op.create_index(
        "ix_loans_invoice_store_sequence",
        "loans",
        ["issued_store_id", "invoice_code", "invoice_sequence"],
        unique=True,
    )
