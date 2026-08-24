"""Add traceable item change events.

Revision ID: 20260824_07
Revises: 20260824_06
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_07"
down_revision = "20260824_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    columns = {column["name"] for column in inspector.get_columns("intelligence_items")}
    if "latest_change_type" not in columns:
        op.add_column("intelligence_items", sa.Column("latest_change_type", sa.String(30), nullable=True))
        op.create_index("ix_intelligence_items_latest_change_type", "intelligence_items", ["latest_change_type"])
    if "item_changes" not in existing:
        op.create_table(
            "item_changes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("intelligence_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("related_item_id", sa.Integer(), sa.ForeignKey("intelligence_items.id"), nullable=True),
            sa.Column("task_run_id", sa.Integer(), sa.ForeignKey("task_runs.id"), nullable=True),
            sa.Column("publication_id", sa.Integer(), sa.ForeignKey("hermes_publications.id"), nullable=True),
            sa.Column("change_type", sa.String(30), nullable=False),
            sa.Column("basis", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_urls_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("before_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("after_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
            sa.Column("idempotency_key", sa.String(200), nullable=False),
            sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("idempotency_key"),
        )
        for column in ("item_id", "task_run_id", "publication_id", "change_type", "status", "idempotency_key"):
            op.create_index(f"ix_item_changes_{column}", "item_changes", [column])
        op.create_index("ix_item_changes_item_detected", "item_changes", ["item_id", "detected_at", "id"])
        op.create_index("ix_item_changes_related_item", "item_changes", ["related_item_id", "detected_at"])


def downgrade() -> None:
    op.drop_table("item_changes")
    op.drop_index("ix_intelligence_items_latest_change_type", table_name="intelligence_items")
    op.drop_column("intelligence_items", "latest_change_type")
