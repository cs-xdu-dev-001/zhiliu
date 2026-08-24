"""Add explainable personalization scores.

Revision ID: 20260824_08
Revises: 20260824_07
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_08"
down_revision = "20260824_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("intelligence_items")}
    if "personalized_score" not in columns:
        op.add_column("intelligence_items", sa.Column("personalized_score", sa.Float(), nullable=True))
        op.add_column("intelligence_items", sa.Column("recommendation_reasons_json", sa.Text(), nullable=False, server_default="[]"))
        op.add_column("intelligence_items", sa.Column("personalization_version", sa.Integer(), nullable=False, server_default="1"))
        op.create_index("ix_intelligence_items_personalized_score", "intelligence_items", ["personalized_score"])
    if "personalization_settings" not in set(inspector.get_table_names()):
        op.create_table("personalization_settings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("auto_learning_enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("algorithm_version", sa.Integer(), nullable=False, server_default="1"), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("personalization_settings")
    op.drop_index("ix_intelligence_items_personalized_score", table_name="intelligence_items")
    op.drop_column("intelligence_items", "personalization_version")
    op.drop_column("intelligence_items", "recommendation_reasons_json")
    op.drop_column("intelligence_items", "personalized_score")
