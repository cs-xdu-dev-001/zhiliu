"""Add task retry lineage.

Revision ID: 20260824_01
Revises: 20260804_02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260824_01"
down_revision = "20260804_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "retry_of_id" not in {column["name"] for column in inspector.get_columns("task_runs")}:
        with op.batch_alter_table("task_runs") as batch:
            batch.add_column(sa.Column("retry_of_id", sa.Integer(), nullable=True))

    inspector = sa.inspect(op.get_bind())
    retry_foreign_key = any(
        foreign_key["constrained_columns"] == ["retry_of_id"]
        and foreign_key["referred_table"] == "task_runs"
        for foreign_key in inspector.get_foreign_keys("task_runs")
    )
    if not retry_foreign_key:
        with op.batch_alter_table("task_runs") as batch:
            batch.create_foreign_key("fk_task_runs_retry_of_id", "task_runs", ["retry_of_id"], ["id"])

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("task_runs")}
    if "ix_task_runs_retry_of_id" not in indexes:
        op.create_index("ix_task_runs_retry_of_id", "task_runs", ["retry_of_id"])
    if "uq_task_runs_active_retry" not in indexes:
        op.create_index(
            "uq_task_runs_active_retry",
            "task_runs",
            ["retry_of_id"],
            unique=True,
            sqlite_where=sa.text(
                "retry_of_id IS NOT NULL AND status IN ('queued', 'running')"
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("task_runs")}
    if "uq_task_runs_active_retry" in indexes:
        op.drop_index("uq_task_runs_active_retry", table_name="task_runs")
    if "ix_task_runs_retry_of_id" in indexes:
        op.drop_index("ix_task_runs_retry_of_id", table_name="task_runs")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("task_runs")}
    if "retry_of_id" in columns:
        with op.batch_alter_table("task_runs") as batch:
            batch.drop_column("retry_of_id")
