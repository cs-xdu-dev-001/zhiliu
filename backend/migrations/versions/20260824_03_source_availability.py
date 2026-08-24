"""Add source availability status.

Revision ID: 20260824_03
Revises: 20260824_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_03"
down_revision = "20260824_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("intelligence_items")}
    if "source_unavailable" not in columns:
        with op.batch_alter_table("intelligence_items") as batch:
            batch.add_column(sa.Column("source_unavailable", sa.Boolean(), nullable=False, server_default=sa.false()))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("intelligence_items")}
    if "ix_intelligence_items_source_unavailable" not in indexes:
        op.create_index("ix_intelligence_items_source_unavailable", "intelligence_items", ["source_unavailable"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("intelligence_items")}
    if "ix_intelligence_items_source_unavailable" in indexes:
        op.drop_index("ix_intelligence_items_source_unavailable", table_name="intelligence_items")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("intelligence_items")}
    if "source_unavailable" in columns:
        with op.batch_alter_table("intelligence_items") as batch:
            batch.drop_column("source_unavailable")
