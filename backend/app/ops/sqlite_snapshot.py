import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

RESTORE_CONFIRMATION = "RESTORE_ZHILIU_SQLITE"


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_database(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("SQLite文件不存在或为空")
    with closing(_connect_read_only(path)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("SQLite完整性检查失败")
        has_migration_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        migration_version = (
            connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
            if has_migration_table
            else None
        )
    return {
        "integrity": "ok",
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "migration_version": migration_version[0] if migration_version else None,
    }


def create_snapshot(source: Path, destination: Path) -> dict[str, object]:
    if source.resolve() == destination.resolve():
        raise ValueError("备份文件不能覆盖源数据库")
    if destination.exists():
        raise FileExistsError("备份目标已存在")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(_connect_read_only(source)) as source_db, closing(sqlite3.connect(destination)) as destination_db:
            source_db.backup(destination_db)
        os.chmod(destination, 0o600)
        return inspect_database(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def restore_snapshot(source: Path, destination: Path, confirmation: str) -> dict[str, object]:
    if confirmation != RESTORE_CONFIRMATION:
        raise ValueError("恢复操作缺少明确确认")
    inspected = inspect_database(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.restore.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with closing(_connect_read_only(source)) as source_db, closing(sqlite3.connect(temporary)) as destination_db:
            source_db.backup(destination_db)
        inspect_database(temporary)
        os.chmod(temporary, 0o600)
        for suffix in ("-wal", "-shm"):
            Path(f"{destination}{suffix}").unlink(missing_ok=True)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return inspected


def main() -> None:
    parser = argparse.ArgumentParser(description="知流SQLite一致性备份与恢复工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("source", type=Path)
    backup.add_argument("destination", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("source", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("source", type=Path)
    restore.add_argument("destination", type=Path)
    restore.add_argument("--confirm", required=True)
    arguments = parser.parse_args()

    if arguments.command == "backup":
        result = create_snapshot(arguments.source, arguments.destination)
    elif arguments.command == "verify":
        result = inspect_database(arguments.source)
    else:
        result = restore_snapshot(arguments.source, arguments.destination, arguments.confirm)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
