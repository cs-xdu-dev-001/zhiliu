#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
BACKUP_PATH="${1:-}"
CONFIRMATION="${2:-}"

if [[ -z "$BACKUP_PATH" ]] || [[ "$CONFIRMATION" != "RESTORE_ZHILIU_SQLITE" ]]; then
  echo "用法：$0 <备份.db> RESTORE_ZHILIU_SQLITE" >&2
  exit 2
fi
if [[ ! -f "$BACKUP_PATH" ]]; then
  echo "备份文件不存在" >&2
  exit 2
fi
BACKUP_DIR="$(cd -- "$(dirname -- "$BACKUP_PATH")" && pwd -P)"
BACKUP_PATH="$BACKUP_DIR/$(basename -- "$BACKUP_PATH")"
CHECKSUM_PATH="${BACKUP_PATH}.sha256"
if [[ ! -f "$CHECKSUM_PATH" ]]; then
  echo "缺少同名.sha256校验文件" >&2
  exit 2
fi

EXPECTED_SHA="$(awk 'NR == 1 {print $1}' "$CHECKSUM_PATH")"
ACTUAL_SHA="$(sha256sum "$BACKUP_PATH" | awk '{print $1}')"
if [[ ! "$EXPECTED_SHA" =~ ^[0-9a-fA-F]{64}$ ]] || [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  echo "备份校验失败，已停止恢复" >&2
  exit 1
fi

cd "$PROJECT_DIR"
IMAGE="$(docker compose images -q backend | head -n 1)"
if [[ -z "$IMAGE" ]]; then
  echo "找不到backend镜像" >&2
  exit 1
fi
docker run --rm -v "$BACKUP_PATH:/backup/input.db:ro" "$IMAGE" \
  python -m app.ops.sqlite_snapshot verify /backup/input.db >/dev/null

SAFETY_DIR="$PROJECT_DIR/backups/pre-restore"
"$SCRIPT_DIR/sqlite-backup.sh" "$SAFETY_DIR"

BACKEND_STOPPED=false
restart_on_error() {
  if [[ "$BACKEND_STOPPED" == true ]]; then
    docker compose up -d backend web >/dev/null 2>&1 || true
  fi
}
trap restart_on_error EXIT

docker compose stop backend
BACKEND_STOPPED=true
docker compose run --rm --no-deps \
  -v "$BACKUP_PATH:/restore/input.db:ro" \
  backend python -m app.ops.sqlite_snapshot restore \
  /restore/input.db /data/zhiliu.db --confirm RESTORE_ZHILIU_SQLITE >/dev/null
docker compose up -d backend web

for _ in $(seq 1 30); do
  if docker compose exec -T backend python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/health', timeout=3)" >/dev/null 2>&1; then
    BACKEND_STOPPED=false
    trap - EXIT
    echo "恢复完成，后端健康检查通过"
    exit 0
  fi
  sleep 2
done

echo "数据库已恢复，但后端健康检查未通过；已保留恢复前安全备份" >&2
exit 1
