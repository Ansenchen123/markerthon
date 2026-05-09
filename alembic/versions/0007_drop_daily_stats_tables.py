"""drop daily stats tables

Revision ID: 0007_drop_daily_stats_tables
Revises: 0006_add_daily_stats_tables
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_drop_daily_stats_tables"
down_revision = "0006_add_daily_stats_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_daily_recovered_stats_container_type"), table_name="daily_recovered_stats")
    op.drop_index(op.f("ix_daily_recovered_stats_store_id"), table_name="daily_recovered_stats")
    op.drop_index(op.f("ix_daily_recovered_stats_stat_date"), table_name="daily_recovered_stats")
    op.drop_table("daily_recovered_stats")
    op.drop_index(op.f("ix_daily_sold_stats_container_type"), table_name="daily_sold_stats")
    op.drop_index(op.f("ix_daily_sold_stats_store_id"), table_name="daily_sold_stats")
    op.drop_index(op.f("ix_daily_sold_stats_stat_date"), table_name="daily_sold_stats")
    op.drop_table("daily_sold_stats")


def downgrade() -> None:
    op.create_table(
        "daily_sold_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("container_type", sa.String(length=20), nullable=False),
        sa.Column("sold_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stat_date", "store_id", "container_type", name="uq_daily_sold_stats_date_store_type"),
    )
    op.create_index(op.f("ix_daily_sold_stats_stat_date"), "daily_sold_stats", ["stat_date"], unique=False)
    op.create_index(op.f("ix_daily_sold_stats_store_id"), "daily_sold_stats", ["store_id"], unique=False)
    op.create_index(op.f("ix_daily_sold_stats_container_type"), "daily_sold_stats", ["container_type"], unique=False)

    op.create_table(
        "daily_recovered_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("container_type", sa.String(length=20), nullable=False),
        sa.Column("recovered_count", sa.Integer(), nullable=False),
        sa.Column("normal_count", sa.Integer(), nullable=False),
        sa.Column("expired_count", sa.Integer(), nullable=False),
        sa.Column("abnormal_count", sa.Integer(), nullable=False),
        sa.Column("cross_store_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stat_date",
            "store_id",
            "container_type",
            name="uq_daily_recovered_stats_date_store_type",
        ),
    )
    op.create_index(op.f("ix_daily_recovered_stats_stat_date"), "daily_recovered_stats", ["stat_date"], unique=False)
    op.create_index(op.f("ix_daily_recovered_stats_store_id"), "daily_recovered_stats", ["store_id"], unique=False)
    op.create_index(
        op.f("ix_daily_recovered_stats_container_type"),
        "daily_recovered_stats",
        ["container_type"],
        unique=False,
    )
