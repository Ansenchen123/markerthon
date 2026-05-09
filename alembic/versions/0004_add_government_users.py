"""add government users

Revision ID: 0004_add_government_users
Revises: 0003_add_invoice_count_fields
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_government_users"
down_revision = "0003_add_invoice_count_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "government_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(op.f("ix_government_users_username"), "government_users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_government_users_username"), table_name="government_users")
    op.drop_table("government_users")
