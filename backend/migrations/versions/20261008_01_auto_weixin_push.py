"""Add per-subscription Weixin delivery and task notification state."""

from alembic import op
import sqlalchemy as sa


revision = "20261008_01"
down_revision = "20260824_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    subscription_columns = {column["name"] for column in inspector.get_columns("subscriptions")}
    if "notify_wechat" not in subscription_columns:
        with op.batch_alter_table("subscriptions") as batch:
            batch.add_column(
                sa.Column("notify_wechat", sa.Boolean(), nullable=False, server_default=sa.false())
            )

    task_columns = {column["name"] for column in inspector.get_columns("task_runs")}
    with op.batch_alter_table("task_runs") as batch:
        if "notification_status" not in task_columns:
            batch.add_column(
                sa.Column("notification_status", sa.String(length=30), nullable=False, server_default="not_requested")
            )
        if "notification_error" not in task_columns:
            batch.add_column(sa.Column("notification_error", sa.Text(), nullable=True))
        if "notification_sent_at" not in task_columns:
            batch.add_column(sa.Column("notification_sent_at", sa.DateTime(timezone=True), nullable=True))
        if "notification_message" not in task_columns:
            batch.add_column(sa.Column("notification_message", sa.Text(), nullable=True))
        if "notification_token" not in task_columns:
            batch.add_column(sa.Column("notification_token", sa.String(36), nullable=True))
        if "notification_claimed_at" not in task_columns:
            batch.add_column(sa.Column("notification_claimed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "task_runs" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("task_runs")}
        with op.batch_alter_table("task_runs") as batch:
            for name in ("notification_claimed_at", "notification_token", "notification_message", "notification_sent_at", "notification_error", "notification_status"):
                if name in columns:
                    batch.drop_column(name)
    if "subscriptions" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("subscriptions")}
        if "notify_wechat" in columns:
            with op.batch_alter_table("subscriptions") as batch:
                batch.drop_column("notify_wechat")
