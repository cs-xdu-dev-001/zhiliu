"""Add task inbox lifecycle fields.

Revision ID: 20260824_04
Revises: 20260824_03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_04"
down_revision = "20260824_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("task_runs")}
    with op.batch_alter_table("task_runs") as batch:
        if "heartbeat_at" not in columns:
            batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        if "cancelled_at" not in columns:
            batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("task_runs")}
    if "ix_task_runs_heartbeat_at" not in indexes:
        op.create_index("ix_task_runs_heartbeat_at", "task_runs", ["heartbeat_at"])


def downgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("task_runs")}
    if "ix_task_runs_heartbeat_at" in indexes:
        op.drop_index("ix_task_runs_heartbeat_at", table_name="task_runs")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("task_runs")}
    with op.batch_alter_table("task_runs") as batch:
        if "cancelled_at" in columns:
            batch.drop_column("cancelled_at")
        if "heartbeat_at" in columns:
            batch.drop_column("heartbeat_at")
