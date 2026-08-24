"""Add report generation lineage and citation state.

Revision ID: 20260824_02
Revises: 20260824_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260824_02"
down_revision = "20260824_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    briefing_columns = {column["name"] for column in inspector.get_columns("briefings")}
    briefing_additions = {
        "series_id": sa.Column("series_id", sa.String(36), nullable=True),
        "version_number": sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        "previous_version_id": sa.Column("previous_version_id", sa.Integer(), nullable=True),
        "generation_task_id": sa.Column("generation_task_id", sa.Integer(), nullable=True),
        "citation_status": sa.Column("citation_status", sa.String(30), nullable=False, server_default="unchecked"),
        "citation_warnings_json": sa.Column("citation_warnings_json", sa.Text(), nullable=False, server_default="[]"),
    }
    missing_briefing = [name for name in briefing_additions if name not in briefing_columns]
    if missing_briefing:
        with op.batch_alter_table("briefings") as batch:
            for name in missing_briefing:
                batch.add_column(briefing_additions[name])

    inspector = sa.inspect(op.get_bind())
    briefing_foreign_keys = {
        tuple(foreign_key["constrained_columns"])
        for foreign_key in inspector.get_foreign_keys("briefings")
    }
    if ("previous_version_id",) not in briefing_foreign_keys:
        with op.batch_alter_table("briefings") as batch:
            batch.create_foreign_key(
                "fk_briefings_previous_version_id", "briefings", ["previous_version_id"], ["id"]
            )
    inspector = sa.inspect(op.get_bind())
    briefing_foreign_keys = {
        tuple(foreign_key["constrained_columns"])
        for foreign_key in inspector.get_foreign_keys("briefings")
    }
    if ("generation_task_id",) not in briefing_foreign_keys:
        with op.batch_alter_table("briefings") as batch:
            batch.create_foreign_key(
                "fk_briefings_generation_task_id", "task_runs", ["generation_task_id"], ["id"]
            )
    briefing_indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("briefings")
    }
    for index_name, column_name in (
        ("ix_briefings_previous_version_id", "previous_version_id"),
        ("ix_briefings_generation_task_id", "generation_task_id"),
        ("ix_briefings_series_id", "series_id"),
    ):
        if index_name not in briefing_indexes:
            op.create_index(index_name, "briefings", [column_name])
    unique_constraints = {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints("briefings")
    }
    if "uq_briefings_series_version" not in unique_constraints:
        with op.batch_alter_table("briefings") as batch:
            batch.create_unique_constraint(
                "uq_briefings_series_version", ["series_id", "version_number"]
            )

    inspector = sa.inspect(op.get_bind())
    task_columns = {column["name"] for column in inspector.get_columns("task_runs")}
    task_additions = {
        "report_item_ids_json": sa.Column("report_item_ids_json", sa.Text(), nullable=True),
        "report_series_id": sa.Column("report_series_id", sa.String(36), nullable=True),
        "report_version_number": sa.Column("report_version_number", sa.Integer(), nullable=True),
    }
    missing_tasks = [name for name in task_additions if name not in task_columns]
    if missing_tasks:
        with op.batch_alter_table("task_runs") as batch:
            for name in missing_tasks:
                batch.add_column(task_additions[name])
    task_indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("task_runs")
    }
    if "ix_task_runs_report_series_id" not in task_indexes:
        op.create_index("ix_task_runs_report_series_id", "task_runs", ["report_series_id"])
    if "uq_task_runs_active_report_series" not in task_indexes:
        op.create_index(
            "uq_task_runs_active_report_series",
            "task_runs",
            ["report_series_id"],
            unique=True,
            sqlite_where=sa.text(
                "origin = 'web-report' AND report_series_id IS NOT NULL "
                "AND status IN ('queued', 'running')"
            ),
        )


def downgrade() -> None:
    task_indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("task_runs")
    }
    if "uq_task_runs_active_report_series" in task_indexes:
        op.drop_index("uq_task_runs_active_report_series", table_name="task_runs")
    if "ix_task_runs_report_series_id" in task_indexes:
        op.drop_index("ix_task_runs_report_series_id", table_name="task_runs")
    task_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("task_runs")}
    removable_tasks = [
        name for name in ("report_version_number", "report_series_id", "report_item_ids_json")
        if name in task_columns
    ]
    if removable_tasks:
        with op.batch_alter_table("task_runs") as batch:
            for name in removable_tasks:
                batch.drop_column(name)

    inspector = sa.inspect(op.get_bind())
    briefing_indexes = {index["name"] for index in inspector.get_indexes("briefings")}
    for index_name in (
        "ix_briefings_series_id",
        "ix_briefings_generation_task_id",
        "ix_briefings_previous_version_id",
    ):
        if index_name in briefing_indexes:
            op.drop_index(index_name, table_name="briefings")
    unique_constraints = {
        constraint["name"] for constraint in sa.inspect(op.get_bind()).get_unique_constraints("briefings")
    }
    foreign_keys = {
        foreign_key["name"]: tuple(foreign_key["constrained_columns"])
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys("briefings")
    }
    briefing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("briefings")}
    with op.batch_alter_table("briefings") as batch:
        if "uq_briefings_series_version" in unique_constraints:
            batch.drop_constraint("uq_briefings_series_version", type_="unique")
        for constraint_name, columns in foreign_keys.items():
            if constraint_name and columns in (("generation_task_id",), ("previous_version_id",)):
                batch.drop_constraint(constraint_name, type_="foreignkey")
        for name in (
            "citation_warnings_json", "citation_status", "generation_task_id",
            "previous_version_id", "version_number", "series_id",
        ):
            if name in briefing_columns:
                batch.drop_column(name)
