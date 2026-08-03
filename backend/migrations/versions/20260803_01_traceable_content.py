"""Add traceable content lineage.

Revision ID: 20260803_01
Revises:
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

from app.db import Base
from app import models  # noqa: F401


revision = "20260803_01"
down_revision = None
branch_labels = None
depends_on = None


def _index_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "subscriptions" not in tables:
        Base.metadata.create_all(bind=bind)
        return

    if "hermes_publications" not in tables:
        HermesPublication = Base.metadata.tables["hermes_publications"]
        HermesPublication.create(bind=bind)
    else:
        columns = {
            column["name"]
            for column in inspector.get_columns("hermes_publications")
        }
        with op.batch_alter_table("hermes_publications") as batch:
            if "trace_id" not in columns:
                batch.add_column(sa.Column("trace_id", sa.String(160), nullable=True))
            if "hermes_run_id" not in columns:
                batch.add_column(sa.Column("hermes_run_id", sa.String(255), nullable=True))
            if "task_run_id" not in columns:
                batch.add_column(sa.Column("task_run_id", sa.Integer(), nullable=True))

        inspector = sa.inspect(bind)
        task_run_foreign_key_exists = any(
            foreign_key["referred_table"] == "task_runs"
            and foreign_key["constrained_columns"] == ["task_run_id"]
            for foreign_key in inspector.get_foreign_keys("hermes_publications")
        )
        if not task_run_foreign_key_exists:
            with op.batch_alter_table("hermes_publications") as batch:
                batch.create_foreign_key(
                    "fk_hermes_publications_task_run_id",
                    "task_runs",
                    ["task_run_id"],
                    ["id"],
                )

        inspector = sa.inspect(bind)
        indexes = _index_names(inspector, "hermes_publications")
        if "ix_hermes_publications_trace_id" not in indexes:
            op.create_index(
                "ix_hermes_publications_trace_id",
                "hermes_publications",
                ["trace_id"],
            )
        if "ix_hermes_publications_hermes_run_id" not in indexes:
            op.create_index(
                "ix_hermes_publications_hermes_run_id",
                "hermes_publications",
                ["hermes_run_id"],
            )
        if "ix_hermes_publications_task_run_id" not in indexes:
            op.create_index(
                "ix_hermes_publications_task_run_id",
                "hermes_publications",
                ["task_run_id"],
            )

    inspector = sa.inspect(bind)
    if "publication_items" not in inspector.get_table_names():
        op.create_table(
            "publication_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "publication_id",
                sa.Integer(),
                sa.ForeignKey("hermes_publications.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "item_id",
                sa.Integer(),
                sa.ForeignKey("intelligence_items.id"),
                nullable=False,
            ),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("was_inserted", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "publication_id",
                "item_id",
                name="uq_publication_items_publication_item",
            ),
        )
        op.create_index(
            "ix_publication_items_publication_id",
            "publication_items",
            ["publication_id"],
        )
        op.create_index(
            "ix_publication_items_item_id",
            "publication_items",
            ["item_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "publication_items" in inspector.get_table_names():
        op.drop_table("publication_items")
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("hermes_publications")
    }
    with op.batch_alter_table("hermes_publications") as batch:
        for name in ("task_run_id", "hermes_run_id", "trace_id"):
            if name in columns:
                batch.drop_column(name)
