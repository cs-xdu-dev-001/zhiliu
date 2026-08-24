"""Add queryable content feedback.

Revision ID: 20260824_10
Revises: 20260824_09
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_10"
down_revision = "20260824_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "content_feedback" in set(inspector.get_table_names()):
        expected_columns = {
            "item_id", "briefing_id", "topic_id", "preference_id", "preference_was_active",
            "feedback_type", "impact_scope", "note", "effect_before_json", "request_hash",
            "idempotency_key", "active", "version", "created_at", "updated_at", "revoked_at",
        }
        actual_columns = {column["name"] for column in inspector.get_columns("content_feedback")}
        expected_constraints = {
            "ck_content_feedback_one_target",
            "ck_content_feedback_type",
            "ck_content_feedback_impact_scope",
        }
        actual_constraints = {constraint["name"] for constraint in inspector.get_check_constraints("content_feedback")}
        if not expected_columns <= actual_columns or not expected_constraints <= actual_constraints:
            raise RuntimeError("content_feedback表已存在但结构不完整，请先备份并检查数据库")
        return
    op.create_table(
        "content_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("intelligence_items.id"), nullable=True),
        sa.Column("briefing_id", sa.Integer(), sa.ForeignKey("briefings.id"), nullable=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("preference_id", sa.Integer(), sa.ForeignKey("hermes_preferences.id"), nullable=True),
        sa.Column("preference_was_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("feedback_type", sa.String(40), nullable=False),
        sa.Column("impact_scope", sa.String(30), nullable=False, server_default="current"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("effect_before_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(item_id IS NOT NULL) != (briefing_id IS NOT NULL)", name="ck_content_feedback_one_target"),
        sa.CheckConstraint("feedback_type IN ('useful','irrelevant','duplicate','summary_wrong','source_unreliable','follow_up')", name="ck_content_feedback_type"),
        sa.CheckConstraint("impact_scope IN ('current','topic','long_term')", name="ck_content_feedback_impact_scope"),
    )
    op.create_index("ix_content_feedback_idempotency_key", "content_feedback", ["idempotency_key"], unique=True)
    op.create_index("ix_content_feedback_item_id", "content_feedback", ["item_id"])
    op.create_index("ix_content_feedback_briefing_id", "content_feedback", ["briefing_id"])
    op.create_index("ix_content_feedback_topic_id", "content_feedback", ["topic_id"])
    op.create_index("ix_content_feedback_preference_id", "content_feedback", ["preference_id"])
    op.create_index("ix_content_feedback_feedback_type", "content_feedback", ["feedback_type"])
    op.create_index("ix_content_feedback_active", "content_feedback", ["active"])
    op.create_index("ix_content_feedback_item_active", "content_feedback", ["item_id", "active", "created_at"])
    op.create_index("ix_content_feedback_briefing_active", "content_feedback", ["briefing_id", "active", "created_at"])


def downgrade() -> None:
    op.drop_table("content_feedback")
