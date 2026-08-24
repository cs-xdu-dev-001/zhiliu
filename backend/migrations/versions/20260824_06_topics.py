"""Add topic and signal center.

Revision ID: 20260824_06
Revises: 20260824_05
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_06"
down_revision = "20260824_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "topics" not in existing:
        op.create_table("topics", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("normalized_name", sa.String(160), nullable=False), sa.Column("description", sa.Text(), nullable=False, server_default=""), sa.Column("is_followed", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_muted", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("merged_into_id", sa.Integer(), sa.ForeignKey("topics.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("normalized_name"))
        for column in ("normalized_name", "is_followed", "is_pinned", "is_muted", "merged_into_id"):
            op.create_index(f"ix_topics_{column}", "topics", [column])
    if "topic_aliases" not in existing:
        op.create_table("topic_aliases", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("normalized_name", sa.String(160), nullable=False), sa.Column("source", sa.String(30), nullable=False, server_default="keyword"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("normalized_name"))
        op.create_index("ix_topic_aliases_topic_id", "topic_aliases", ["topic_id"]); op.create_index("ix_topic_aliases_normalized_name", "topic_aliases", ["normalized_name"])
    if "item_topics" not in existing:
        op.create_table("item_topics", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("item_id", sa.Integer(), sa.ForeignKey("intelligence_items.id", ondelete="CASCADE"), nullable=False), sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False), sa.Column("source", sa.String(30), nullable=False, server_default="keyword"), sa.Column("confidence", sa.Float(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("item_id", "topic_id", name="uq_item_topics_item_topic"))
        op.create_index("ix_item_topics_item_id", "item_topics", ["item_id"]); op.create_index("ix_item_topics_topic_id", "item_topics", ["topic_id"])


def downgrade() -> None:
    op.drop_table("item_topics"); op.drop_table("topic_aliases"); op.drop_table("topics")
