"""Add daily attention settings.

Revision ID: 20260824_09
Revises: 20260824_08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_09"
down_revision = "20260824_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("personalization_settings")}
    if "daily_min_importance" not in columns:
        op.add_column("personalization_settings", sa.Column("daily_min_importance", sa.Float(), nullable=False, server_default="0.7"))
    if "daily_important_only" not in columns:
        op.add_column("personalization_settings", sa.Column("daily_important_only", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("personalization_settings", "daily_important_only")
    op.drop_column("personalization_settings", "daily_min_importance")
