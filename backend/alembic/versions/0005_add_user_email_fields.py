"""add user email fields

Revision ID: 0005_add_user_email_fields
Revises: 0004_add_government_users
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_user_email_fields"
down_revision = "0004_add_government_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("merchant_users", sa.Column("user_email", sa.String(length=255), nullable=True))
    op.add_column("government_users", sa.Column("user_email", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE merchant_users
        SET user_email = CASE
            WHEN username LIKE '%@%' THEN lower(username)
            ELSE lower(username || '@example.local')
        END
        WHERE user_email IS NULL
        """
    )
    op.execute(
        """
        UPDATE government_users
        SET user_email = CASE
            WHEN username LIKE '%@%' THEN lower(username)
            ELSE lower(username || '@example.local')
        END
        WHERE user_email IS NULL
        """
    )
    op.create_index(op.f("ix_merchant_users_user_email"), "merchant_users", ["user_email"], unique=True)
    op.create_index(op.f("ix_government_users_user_email"), "government_users", ["user_email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_government_users_user_email"), table_name="government_users")
    op.drop_index(op.f("ix_merchant_users_user_email"), table_name="merchant_users")
    op.drop_column("government_users", "user_email")
    op.drop_column("merchant_users", "user_email")
