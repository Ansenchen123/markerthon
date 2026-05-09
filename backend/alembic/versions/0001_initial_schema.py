"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_stores_code"), "stores", ["code"], unique=True)

    op.create_table(
        "merchant_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(op.f("ix_merchant_users_store_id"), "merchant_users", ["store_id"], unique=False)
    op.create_index(op.f("ix_merchant_users_username"), "merchant_users", ["username"], unique=True)

    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("qr_token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_store_id", sa.Integer(), nullable=False),
        sa.Column("invoice_code", sa.String(length=80), nullable=False),
        sa.Column("container_type", sa.String(length=20), nullable=False),
        sa.Column("deposit_amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("returned_at", sa.DateTime(), nullable=True),
        sa.Column("returned_store_id", sa.Integer(), nullable=True),
        sa.Column("return_condition", sa.String(length=20), nullable=True),
        sa.Column("abnormal_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["issued_store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["returned_store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("qr_token_hash", name="uq_loans_qr_token_hash"),
    )
    op.create_index(op.f("ix_loans_container_type"), "loans", ["container_type"], unique=False)
    op.create_index(op.f("ix_loans_due_at"), "loans", ["due_at"], unique=False)
    op.create_index(op.f("ix_loans_invoice_code"), "loans", ["invoice_code"], unique=False)
    op.create_index(op.f("ix_loans_issued_at"), "loans", ["issued_at"], unique=False)
    op.create_index(op.f("ix_loans_issued_store_id"), "loans", ["issued_store_id"], unique=False)
    op.create_index(op.f("ix_loans_qr_token_hash"), "loans", ["qr_token_hash"], unique=False)
    op.create_index(op.f("ix_loans_returned_at"), "loans", ["returned_at"], unique=False)
    op.create_index(op.f("ix_loans_returned_store_id"), "loans", ["returned_store_id"], unique=False)
    op.create_index(op.f("ix_loans_status"), "loans", ["status"], unique=False)

    op.create_table(
        "refund_ledgers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("refund_amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loan_id"),
    )
    op.create_index(op.f("ix_refund_ledgers_created_at"), "refund_ledgers", ["created_at"], unique=False)
    op.create_index(op.f("ix_refund_ledgers_loan_id"), "refund_ledgers", ["loan_id"], unique=True)
    op.create_index(op.f("ix_refund_ledgers_store_id"), "refund_ledgers", ["store_id"], unique=False)

    op.create_table(
        "scan_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("qr_token_hash", sa.String(length=64), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=True),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scan_events_created_at"), "scan_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_scan_events_loan_id"), "scan_events", ["loan_id"], unique=False)
    op.create_index(op.f("ix_scan_events_qr_token_hash"), "scan_events", ["qr_token_hash"], unique=False)
    op.create_index(op.f("ix_scan_events_reason"), "scan_events", ["reason"], unique=False)
    op.create_index(op.f("ix_scan_events_result"), "scan_events", ["result"], unique=False)
    op.create_index(op.f("ix_scan_events_store_id"), "scan_events", ["store_id"], unique=False)


def downgrade() -> None:
    op.drop_table("scan_events")
    op.drop_table("refund_ledgers")
    op.drop_table("loans")
    op.drop_table("merchant_users")
    op.drop_table("stores")
