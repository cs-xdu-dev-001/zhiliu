#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
BACKUP_DIR="${1:-$PROJECT_DIR/backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="zhiliu-${TIMESTAMP}.db"
CONTAINER_PATH="/data/.${BACKUP_NAME}.tmp"

mkdir -p -- "$BACKUP_DIR"
BACKUP_DIR="$(cd -- "$BACKUP_DIR" && pwd -P)"
chmod 700 "$BACKUP_DIR"
FINAL_PATH="$BACKUP_DIR/$BACKUP_NAME"
HOST_TEMP="$BACKUP_DIR/.${BACKUP_NAME}.tmp"

cd "$PROJECT_DIR"
CONTAINER_ID="$(docker compose ps -q backend)"
if [[ -z "$CONTAINER_ID" ]] || ! docker inspect -f '{{.State.Running}}' "$CONTAINER_ID" | grep -qx true; then
  echo "backend容器未运行，无法创建在线一致性备份" >&2
  exit 1
fi

cleanup() {
  rm -f -- "$HOST_TEMP"
  docker compose exec -T backend rm -f -- "$CONTAINER_PATH" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose exec -T backend \
  python -m app.ops.sqlite_snapshot backup /data/zhiliu.db "$CONTAINER_PATH" >/dev/null
docker cp "$CONTAINER_ID:$CONTAINER_PATH" "$HOST_TEMP" >/dev/null
docker run --rm -v "$HOST_TEMP:/backup/input.db:ro" "$(docker inspect -f '{{.Config.Image}}' "$CONTAINER_ID")" \
  python -m app.ops.sqlite_snapshot verify /backup/input.db >/dev/null
chmod 600 "$HOST_TEMP"
mv -- "$HOST_TEMP" "$FINAL_PATH"
(
  cd "$BACKUP_DIR"
  sha256sum "$BACKUP_NAME" > "${BACKUP_NAME}.sha256"
  chmod 600 "${BACKUP_NAME}.sha256"
)

echo "备份完成：$FINAL_PATH"
echo "校验文件：${FINAL_PATH}.sha256"
