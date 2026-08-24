"""Add tags, saved views, bulk receipts, and governance indexes.

Revision ID: 20260824_05
Revises: 20260824_04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_05"
down_revision = "20260824_04"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _table_names()
    if "item_tags" not in tables:
        op.create_table(
            "item_tags",
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["intelligence_items.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("item_id", "name"),
        )
        op.create_index("ix_item_tags_name_item", "item_tags", ["name", "item_id"])
    if "saved_views" not in tables:
        op.create_table(
            "saved_views",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("query_string", sa.String(length=1500), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_saved_views_name", "saved_views", ["name"], unique=True)
    if "item_bulk_operations" not in tables:
        op.create_table(
            "item_bulk_operations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=160), nullable=False),
            sa.Column("request_hash", sa.String(length=64), nullable=False),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_item_bulk_operations_idempotency_key",
            "item_bulk_operations",
            ["idempotency_key"],
            unique=True,
        )

    item_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("intelligence_items")}
    if "ix_intelligence_items_feed_default" not in item_indexes:
        op.create_index(
            "ix_intelligence_items_feed_default",
            "intelligence_items",
            ["is_invalid", "merged_into_id", "importance", "created_at", "id"],
        )
    revision_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("item_revisions")}
    if "ix_item_revisions_item_created" not in revision_indexes:
        op.create_index(
            "ix_item_revisions_item_created",
            "item_revisions",
            ["item_id", "created_at", "id"],
        )


def downgrade() -> None:
    tables = _table_names()
    if "item_revisions" in tables:
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("item_revisions")}
        if "ix_item_revisions_item_created" in indexes:
            op.drop_index("ix_item_revisions_item_created", table_name="item_revisions")
    if "intelligence_items" in tables:
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("intelligence_items")}
        if "ix_intelligence_items_feed_default" in indexes:
            op.drop_index("ix_intelligence_items_feed_default", table_name="intelligence_items")
    if "item_bulk_operations" in tables:
        op.drop_table("item_bulk_operations")
    if "saved_views" in tables:
        op.drop_table("saved_views")
    if "item_tags" in tables:
        op.drop_table("item_tags")
