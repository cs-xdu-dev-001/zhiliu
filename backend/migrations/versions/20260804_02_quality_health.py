"""Add content quality decisions and retry counters.

Revision ID: 20260804_02
Revises: 20260804_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260804_02"
down_revision = "20260804_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "retry_count" not in {column["name"] for column in inspector.get_columns("task_runs")}:
        with op.batch_alter_table("task_runs") as batch:
            batch.add_column(sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    if "hermes_quality_decisions" not in inspector.get_table_names():
        op.create_table(
            "hermes_quality_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("publication_id", sa.Integer(), sa.ForeignKey("hermes_publications.id", ondelete="CASCADE"), nullable=False),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("intelligence_items.id"), nullable=True),
            sa.Column("action", sa.String(30), nullable=False),
            sa.Column("reason_code", sa.String(40), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("url", sa.String(1000), nullable=False),
            sa.Column("source", sa.String(120), nullable=False),
            sa.Column("keywords_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("importance", sa.Float(), nullable=False, server_default="0"),
            sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_hermes_quality_decisions_publication_id", "hermes_quality_decisions", ["publication_id"])
        op.create_index("ix_hermes_quality_decisions_item_id", "hermes_quality_decisions", ["item_id"])
        op.create_index("ix_hermes_quality_decisions_action", "hermes_quality_decisions", ["action"])
        op.create_index("ix_hermes_quality_decisions_kind", "hermes_quality_decisions", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_hermes_quality_decisions_kind", table_name="hermes_quality_decisions")
    op.drop_index("ix_hermes_quality_decisions_action", table_name="hermes_quality_decisions")
    op.drop_index("ix_hermes_quality_decisions_item_id", table_name="hermes_quality_decisions")
    op.drop_index("ix_hermes_quality_decisions_publication_id", table_name="hermes_quality_decisions")
    op.drop_table("hermes_quality_decisions")
    with op.batch_alter_table("task_runs") as batch:
        batch.drop_column("retry_count")
