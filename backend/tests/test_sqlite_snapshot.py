import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.ops.sqlite_snapshot import (
    RESTORE_CONFIRMATION,
    create_snapshot,
    inspect_database,
    restore_snapshot,
)


def create_database(path: Path, value: str) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records VALUES (?)", (value,))
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('20260824_ops')")
        connection.commit()


def read_value(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT value FROM records").fetchone()[0]


def test_snapshot_is_consistent_and_preserves_migration_version(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    create_database(source, "before")

    result = create_snapshot(source, backup)
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE records SET value='after'")
        connection.commit()

    assert result["integrity"] == "ok"
    assert result["migration_version"] == "20260824_ops"
    assert len(str(result["sha256"])) == 64
    assert read_value(backup) == "before"


def test_snapshot_refuses_overwrite_and_removes_partial_output(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    create_database(source, "safe")
    backup.write_text("do not replace", encoding="utf-8")

    with pytest.raises(FileExistsError, match="目标已存在"):
        create_snapshot(source, backup)

    assert backup.read_text(encoding="utf-8") == "do not replace"


def test_restore_requires_confirmation_and_replaces_database_atomically(tmp_path: Path) -> None:
    source = tmp_path / "backup.db"
    target = tmp_path / "live.db"
    create_database(source, "restored")
    create_database(target, "current")
    Path(f"{target}-wal").write_bytes(b"stale wal")
    Path(f"{target}-shm").write_bytes(b"stale shm")

    with pytest.raises(ValueError, match="明确确认"):
        restore_snapshot(source, target, "")
    assert read_value(target) == "current"

    result = restore_snapshot(source, target, RESTORE_CONFIRMATION)

    assert result["integrity"] == "ok"
    assert inspect_database(target)["integrity"] == "ok"
    assert read_value(target) == "restored"
    assert not Path(f"{target}-wal").exists()
    assert not Path(f"{target}-shm").exists()


def test_verify_rejects_non_sqlite_file(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.db"
    invalid.write_text("not sqlite", encoding="utf-8")

    with pytest.raises(sqlite3.DatabaseError):
        inspect_database(invalid)
