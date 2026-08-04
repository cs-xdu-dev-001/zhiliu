"""Add full-text search and Hermes preferences.

Revision ID: 20260804_01
Revises: 20260803_03
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_01"
down_revision = "20260803_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    publication_columns = {
        column["name"] for column in inspector.get_columns("hermes_publications")
    }
    if "filtered_count" not in publication_columns:
        with op.batch_alter_table("hermes_publications") as batch:
            batch.add_column(
                sa.Column("filtered_count", sa.Integer(), nullable=False, server_default="0")
            )

    if "hermes_preferences" not in inspector.get_table_names():
        op.create_table(
            "hermes_preferences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scope", sa.String(30), nullable=False),
            sa.Column("effect", sa.String(30), nullable=False),
            sa.Column("value", sa.String(300), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False, server_default="all"),
            sa.Column("note", sa.String(1000), nullable=False, server_default=""),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "scope", "effect", "value", "kind", name="uq_hermes_preferences_rule"
            ),
        )
        op.create_index("ix_hermes_preferences_scope", "hermes_preferences", ["scope"])
        op.create_index("ix_hermes_preferences_effect", "hermes_preferences", ["effect"])
        op.create_index("ix_hermes_preferences_kind", "hermes_preferences", ["kind"])
        op.create_index("ix_hermes_preferences_active", "hermes_preferences", ["active"])

    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS intelligence_items_fts USING fts5("
        "title, summary, source, keywords_json, reason, "
        "content='intelligence_items', content_rowid='id', tokenize='trigram')"
    )
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS briefings_fts USING fts5("
        "title, content, content='briefings', content_rowid='id', tokenize='trigram')"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS intelligence_items_fts_ai AFTER INSERT ON intelligence_items BEGIN "
        "INSERT INTO intelligence_items_fts(rowid,title,summary,source,keywords_json,reason) "
        "VALUES(new.id,new.title,new.summary,new.source,new.keywords_json,new.reason); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS intelligence_items_fts_ad AFTER DELETE ON intelligence_items BEGIN "
        "INSERT INTO intelligence_items_fts(intelligence_items_fts,rowid,title,summary,source,keywords_json,reason) "
        "VALUES('delete',old.id,old.title,old.summary,old.source,old.keywords_json,old.reason); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS intelligence_items_fts_au AFTER UPDATE ON intelligence_items BEGIN "
        "INSERT INTO intelligence_items_fts(intelligence_items_fts,rowid,title,summary,source,keywords_json,reason) "
        "VALUES('delete',old.id,old.title,old.summary,old.source,old.keywords_json,old.reason); "
        "INSERT INTO intelligence_items_fts(rowid,title,summary,source,keywords_json,reason) "
        "VALUES(new.id,new.title,new.summary,new.source,new.keywords_json,new.reason); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS briefings_fts_ai AFTER INSERT ON briefings BEGIN "
        "INSERT INTO briefings_fts(rowid,title,content) VALUES(new.id,new.title,new.content); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS briefings_fts_ad AFTER DELETE ON briefings BEGIN "
        "INSERT INTO briefings_fts(briefings_fts,rowid,title,content) "
        "VALUES('delete',old.id,old.title,old.content); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS briefings_fts_au AFTER UPDATE ON briefings BEGIN "
        "INSERT INTO briefings_fts(briefings_fts,rowid,title,content) "
        "VALUES('delete',old.id,old.title,old.content); "
        "INSERT INTO briefings_fts(rowid,title,content) VALUES(new.id,new.title,new.content); END"
    )
    op.execute("INSERT INTO intelligence_items_fts(intelligence_items_fts) VALUES('rebuild')")
    op.execute("INSERT INTO briefings_fts(briefings_fts) VALUES('rebuild')")


def downgrade() -> None:
    for trigger in (
        "intelligence_items_fts_ai",
        "intelligence_items_fts_ad",
        "intelligence_items_fts_au",
        "briefings_fts_ai",
        "briefings_fts_ad",
        "briefings_fts_au",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS intelligence_items_fts")
    op.execute("DROP TABLE IF EXISTS briefings_fts")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "hermes_preferences" in inspector.get_table_names():
        op.drop_table("hermes_preferences")
    publication_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("hermes_publications")
    }
    if "filtered_count" in publication_columns:
        with op.batch_alter_table("hermes_publications") as batch:
            batch.drop_column("filtered_count")
