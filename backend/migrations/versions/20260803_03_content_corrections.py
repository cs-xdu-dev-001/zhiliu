"""Add content corrections and revision history.

Revision ID: 20260803_03
Revises: 20260803_02
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

from app import models  # noqa: F401
from app.db import Base


revision = "20260803_03"
down_revision = "20260803_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "intelligence_items" not in inspector.get_table_names():
        Base.metadata.tables["intelligence_items"].create(bind=bind)
    else:
        columns = {column["name"] for column in inspector.get_columns("intelligence_items")}
        with op.batch_alter_table("intelligence_items") as batch:
            if "is_invalid" not in columns:
                batch.add_column(
                    sa.Column("is_invalid", sa.Boolean(), nullable=False, server_default=sa.false())
                )
            if "merged_into_id" not in columns:
                batch.add_column(sa.Column("merged_into_id", sa.Integer(), nullable=True))

        inspector = sa.inspect(bind)
        has_merge_fk = any(
            foreign_key["constrained_columns"] == ["merged_into_id"]
            and foreign_key["referred_table"] == "intelligence_items"
            for foreign_key in inspector.get_foreign_keys("intelligence_items")
        )
        if not has_merge_fk:
            with op.batch_alter_table("intelligence_items") as batch:
                batch.create_foreign_key(
                    "fk_intelligence_items_merged_into_id",
                    "intelligence_items",
                    ["merged_into_id"],
                    ["id"],
                )

        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("intelligence_items")}
        if "ix_intelligence_items_is_invalid" not in indexes:
            op.create_index("ix_intelligence_items_is_invalid", "intelligence_items", ["is_invalid"])
        if "ix_intelligence_items_merged_into_id" not in indexes:
            op.create_index("ix_intelligence_items_merged_into_id", "intelligence_items", ["merged_into_id"])

    if "item_revisions" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "item_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "item_id",
                sa.Integer(),
                sa.ForeignKey("intelligence_items.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("action", sa.String(40), nullable=False),
            sa.Column("before_json", sa.Text(), nullable=False),
            sa.Column("after_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_item_revisions_item_id", "item_revisions", ["item_id"])
        op.create_index("ix_item_revisions_action", "item_revisions", ["action"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "item_revisions" in inspector.get_table_names():
        op.drop_table("item_revisions")
    if "intelligence_items" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("intelligence_items")}
    for name in ("ix_intelligence_items_merged_into_id", "ix_intelligence_items_is_invalid"):
        if name in indexes:
            op.drop_index(name, table_name="intelligence_items")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("intelligence_items")}
    with op.batch_alter_table("intelligence_items") as batch:
        for name in ("merged_into_id", "is_invalid"):
            if name in columns:
                batch.drop_column(name)
