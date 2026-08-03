"""Add task feedback fields.

Revision ID: 20260803_02
Revises: 20260803_01
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

from app.db import Base
from app import models  # noqa: F401


revision = "20260803_02"
down_revision = "20260803_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_runs" not in inspector.get_table_names():
        Base.metadata.tables["task_runs"].create(bind=bind)
        return

    columns = {column["name"] for column in inspector.get_columns("task_runs")}
    with op.batch_alter_table("task_runs") as batch:
        if "trace_id" not in columns:
            batch.add_column(sa.Column("trace_id", sa.String(160), nullable=True))
        if "origin" not in columns:
            batch.add_column(
                sa.Column(
                    "origin",
                    sa.String(40),
                    nullable=False,
                    server_default="subscription-hermes",
                )
            )
        if "topic" not in columns:
            batch.add_column(sa.Column("topic", sa.String(200), nullable=True))
        if "request_summary" not in columns:
            batch.add_column(sa.Column("request_summary", sa.String(1000), nullable=True))
        if "stage" not in columns:
            batch.add_column(
                sa.Column("stage", sa.String(40), nullable=False, server_default="accepted")
            )
        if "result_summary" not in columns:
            batch.add_column(sa.Column("result_summary", sa.Text(), nullable=True))
        if "hermes_run_id" in columns:
            batch.alter_column(
                "hermes_run_id",
                existing_type=sa.String(80),
                type_=sa.String(255),
                existing_nullable=True,
            )

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("task_runs")}
    if "ix_task_runs_trace_id" not in indexes:
        op.create_index(
            "ix_task_runs_trace_id",
            "task_runs",
            ["trace_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_runs" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("task_runs")}
    if "ix_task_runs_trace_id" in indexes:
        op.drop_index("ix_task_runs_trace_id", table_name="task_runs")
    columns = {column["name"] for column in inspector.get_columns("task_runs")}
    with op.batch_alter_table("task_runs") as batch:
        if "hermes_run_id" in columns:
            batch.alter_column(
                "hermes_run_id",
                existing_type=sa.String(255),
                type_=sa.String(80),
                existing_nullable=True,
            )
        for name in (
            "result_summary",
            "stage",
            "request_summary",
            "topic",
            "origin",
            "trace_id",
        ):
            if name in columns:
                batch.drop_column(name)
