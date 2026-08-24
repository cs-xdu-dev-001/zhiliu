"""Add auditable content import batches.

Revision ID: 20260824_11
Revises: 20260824_10
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_11"
down_revision = "20260824_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "import_batches" not in tables:
        op.create_table(
            "import_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_key", sa.String(64), nullable=False),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False),
            sa.Column("report_conflict", sa.String(30), nullable=False, server_default="keep"),
            sa.Column("status", sa.String(20), nullable=False, server_default="committed"),
            sa.Column("counts_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("status IN ('committed','undone')", name="ck_import_batches_status"),
            sa.CheckConstraint("report_conflict IN ('keep','new_version')", name="ck_import_batches_report_conflict"),
        )
        op.create_index("ix_import_batches_import_key", "import_batches", ["import_key"])
        op.create_index("ix_import_batches_payload_hash", "import_batches", ["payload_hash"])
        op.create_index("ix_import_batches_status", "import_batches", ["status"])
        op.create_index(
            "uq_import_batches_active_key",
            "import_batches",
            ["import_key"],
            unique=True,
            sqlite_where=sa.text("status = 'committed'"),
        )
    if "import_batch_records" not in tables:
        op.create_table(
            "import_batch_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("entity_type", sa.String(40), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("target_key", sa.String(240), nullable=False),
            sa.Column("after_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("batch_id", "entity_type", "target_key", name="uq_import_batch_record_target"),
        )
        op.create_index("ix_import_batch_records_batch_id", "import_batch_records", ["batch_id"])
        op.create_index("ix_import_batch_records_entity_type", "import_batch_records", ["entity_type"])


def downgrade() -> None:
    op.drop_table("import_batch_records")
    op.drop_table("import_batches")
