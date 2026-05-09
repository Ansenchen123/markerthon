"""add invoice count fields

Revision ID: 0003_add_invoice_count_fields
Revises: 0002_add_invoice_sequence
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_invoice_count_fields"
down_revision = "0002_add_invoice_sequence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("loans", sa.Column("cup_count", sa.Integer(), nullable=True))
    op.add_column("loans", sa.Column("returned_count", sa.Integer(), nullable=True))
    op.execute("UPDATE loans SET cup_count = 1 WHERE cup_count IS NULL")
    op.execute("UPDATE loans SET returned_count = CASE WHEN status = 'returned' THEN 1 ELSE 0 END WHERE returned_count IS NULL")


def downgrade() -> None:
    op.drop_column("loans", "returned_count")
    op.drop_column("loans", "cup_count")
