#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
LOCAL_BASE_URL="${LOCAL_BASE_URL:-http://127.0.0.1:8080}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"

cd "$PROJECT_DIR"
docker compose config --quiet
docker compose ps --status running backend web >/dev/null

curl --fail --silent --show-error "$LOCAL_BASE_URL/api/health" >/dev/null
curl --fail --silent --show-error "$LOCAL_BASE_URL/api/diagnostics" >/dev/null

MCP_STATUS="$(curl --silent --output /dev/null --write-out '%{http_code}' "$LOCAL_BASE_URL/api/mcp")"
if [[ "$MCP_STATUS" != "401" ]]; then
  echo "本机未认证MCP预期返回401，实际为$MCP_STATUS" >&2
  exit 1
fi

if [[ -n "$PUBLIC_BASE_URL" ]]; then
  PUBLIC_MCP_STATUS="$(curl --silent --output /dev/null --write-out '%{http_code}' "${PUBLIC_BASE_URL%/}/api/mcp")"
  if [[ "$PUBLIC_MCP_STATUS" != "404" ]]; then
    echo "公网MCP预期返回404，实际为$PUBLIC_MCP_STATUS" >&2
    exit 1
  fi
fi

docker compose exec -T backend python -m app.ops.sqlite_snapshot verify /data/zhiliu.db >/dev/null
echo "部署验收通过"
