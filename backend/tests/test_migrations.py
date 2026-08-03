import sqlite3
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def upgrade(database_path: Path) -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "alembic",
            "-c",
            "alembic.ini",
            "-x",
            f"database_url=sqlite:///{database_path.as_posix()}",
            "upgrade",
            "head",
        ],
        cwd=BACKEND_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_empty_database_is_upgraded_to_traceable_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.db"

    upgrade(database_path)

    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert "publication_items" in inspector.get_table_names()
    publication_columns = {
        column["name"] for column in inspector.get_columns("hermes_publications")
    }
    assert {"trace_id", "hermes_run_id", "task_run_id"} <= publication_columns
    publication_foreign_keys = inspector.get_foreign_keys("hermes_publications")
    assert any(
        foreign_key["referred_table"] == "task_runs"
        and foreign_key["constrained_columns"] == ["task_run_id"]
        for foreign_key in publication_foreign_keys
    )
    assert "alembic_version" in inspector.get_table_names()


def test_existing_database_keeps_data_during_upgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "existing.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            kind VARCHAR(30) NOT NULL,
            keywords_json TEXT NOT NULL,
            schedule VARCHAR(80) NOT NULL,
            prompt TEXT NOT NULL,
            enabled BOOLEAN NOT NULL,
            last_run_at DATETIME,
            next_run_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE briefings (
            id INTEGER PRIMARY KEY,
            subscription_id INTEGER NOT NULL,
            title VARCHAR(300) NOT NULL,
            kind VARCHAR(30) NOT NULL,
            content TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            period_start DATETIME,
            period_end DATETIME,
            created_at DATETIME NOT NULL
        );
        CREATE TABLE hermes_publications (
            id INTEGER PRIMARY KEY,
            idempotency_key VARCHAR(160) NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            subscription_id INTEGER NOT NULL,
            briefing_id INTEGER,
            item_count INTEGER NOT NULL,
            skipped_count INTEGER NOT NULL,
            topic VARCHAR(200) NOT NULL,
            request_summary VARCHAR(1000) NOT NULL,
            origin VARCHAR(40) NOT NULL,
            created_at DATETIME NOT NULL
        );
        INSERT INTO subscriptions VALUES (
            1, '保留订阅', 'news', '[]', '0 8 * * *', '保留提示词', 1,
            NULL, NULL, '2026-08-01 00:00:00', '2026-08-01 00:00:00'
        );
        INSERT INTO briefings VALUES (
            1, 1, '历史报告', 'news', '历史正文', 0, NULL, NULL,
            '2026-08-01 00:00:00'
        );
        INSERT INTO hermes_publications VALUES (
            1, 'legacy-key', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            1, 1, 0, 0, '历史主题', '历史摘要', 'weixin-hermes',
            '2026-08-01 00:00:00'
        );
        """
    )
    connection.commit()
    connection.close()

    upgrade(database_path)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as upgraded:
        assert upgraded.scalar(text("SELECT name FROM subscriptions WHERE id = 1")) == "保留订阅"
        row = upgraded.execute(
            text(
                "SELECT trace_id, hermes_run_id, task_run_id "
                "FROM hermes_publications WHERE id = 1"
            )
        ).one()
        assert row == (None, None, None)
    foreign_keys = inspect(engine).get_foreign_keys("hermes_publications")
    assert any(
        foreign_key["referred_table"] == "task_runs"
        and foreign_key["constrained_columns"] == ["task_run_id"]
        for foreign_key in foreign_keys
    )
