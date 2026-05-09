"""rename cup count to item count

Revision ID: 0009_rename_cup_count_to_item_count
Revises: 0008_include_container_type_in_qr
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_rename_cup_count_to_item_count"
down_revision = "0008_include_container_type_in_qr"
branch_labels = None
depends_on = None


def _column_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("loans")}


def upgrade() -> None:
    columns = _column_names()
    if "item_count" not in columns and "cup_count" in columns:
        op.execute("ALTER TABLE loans RENAME COLUMN cup_count TO item_count")


def downgrade() -> None:
    columns = _column_names()
    if "cup_count" not in columns and "item_count" in columns:
        op.execute("ALTER TABLE loans RENAME COLUMN item_count TO cup_count")
