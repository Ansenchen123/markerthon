"""add invoice sequence

Revision ID: 0002_add_invoice_sequence
Revises: 0001_initial_schema
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_invoice_sequence"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("loans", sa.Column("invoice_sequence", sa.Integer(), nullable=True))
    op.execute("UPDATE loans SET invoice_sequence = id WHERE invoice_sequence IS NULL")
    op.create_index(
        "ix_loans_invoice_store_sequence",
        "loans",
        ["issued_store_id", "invoice_code", "invoice_sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_loans_invoice_store_sequence", table_name="loans")
    op.drop_column("loans", "invoice_sequence")
