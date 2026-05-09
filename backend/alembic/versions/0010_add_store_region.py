"""add store region

Revision ID: 0010_add_store_region
Revises: 0009_rename_cup_count_to_item_count
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_store_region"
down_revision = "0009_rename_cup_count_to_item_count"
branch_labels = None
depends_on = None


def _column_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("stores")}


def _index_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes("stores")}


def upgrade() -> None:
    columns = _column_names()
    if "region" not in columns:
        op.add_column("stores", sa.Column("region", sa.String(length=80), nullable=True))
        op.execute("UPDATE stores SET region = '未設定' WHERE region IS NULL OR region = ''")
    if "ix_stores_region" not in _index_names():
        op.create_index(op.f("ix_stores_region"), "stores", ["region"], unique=False)


def downgrade() -> None:
    if "ix_stores_region" in _index_names():
        op.drop_index(op.f("ix_stores_region"), table_name="stores")
    columns = _column_names()
    if "region" in columns:
        op.drop_column("stores", "region")
