"""add remaining count

Revision ID: 0011_add_remaining_count
Revises: 0010_add_store_region
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_remaining_count"
down_revision = "0010_add_store_region"
branch_labels = None
depends_on = None


def _column_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("loans")}


def upgrade() -> None:
    columns = _column_names()
    if "remaining_count" not in columns:
        op.add_column("loans", sa.Column("remaining_count", sa.Integer(), nullable=True))
        op.execute(
            """
            UPDATE loans
            SET remaining_count = MAX(item_count - returned_count, 0)
            WHERE remaining_count IS NULL
            """
        )


def downgrade() -> None:
    columns = _column_names()
    if "remaining_count" in columns:
        op.drop_column("loans", "remaining_count")
