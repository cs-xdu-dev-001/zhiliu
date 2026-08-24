from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_mcp_token_is_wired_into_compose() -> None:
    assert "ZHILIU_MCP_TOKEN=" in read(".env.example")
    assert "ZHILIU_MCP_TOKEN:" in read("docker-compose.yml")


def test_hermes_assets_use_authenticated_local_mcp() -> None:
    config = read("deploy/hermes/mcp-zhiliu.yaml.example")
    assert "http://127.0.0.1:8080/api/mcp" in config
    assert 'Authorization: "Bearer ${ZHILIU_MCP_TOKEN}"' in config
    assert "zhiliu_publish" in config
    assert "zhiliu_begin_task" in config
    assert "zhiliu_report_failure" in config
    assert "zhiliu_create_monitor" in config
    assert "zhiliu_search" in config
    assert "zhiliu_get_preferences" in config
    assert "zhiliu_save_preference" in config
    assert "zhiliu_remove_preference" in config
    assert "zhiliu_update_item" in config

    skill = read("deploy/hermes/skills/zhiliu-publisher/SKILL.md")
    assert "先完成理解、检索、核验和整理" in skill
    assert "不要要求固定前缀" in skill
    assert "微信用户ID" in skill
    assert "traceId" in skill
    assert "重试" in skill
    assert "traceUrl" in skill
    assert "taskUrl" in skill
    assert "briefingUrl" in skill
    assert "长期偏好" in skill
    assert "zhiliu_search" in skill
    assert "sourceUnavailable=true" in skill
    assert "changeType" in skill
    assert "changeBasis" in skill
    assert "relatedItemId" in skill
    assert "sourceUrls" in skill


def test_nginx_has_dedicated_streaming_mcp_proxy() -> None:
    nginx = read("deploy/nginx.conf")
    mcp_location = nginx.index("location ^~ /api/mcp")
    api_location = nginx.index("location /api/")
    assert mcp_location < api_location
    assert "proxy_set_header Authorization $http_authorization;" in nginx
    assert "proxy_buffering off;" in nginx


def test_readme_warns_to_merge_config_and_separate_tokens() -> None:
    readme = read("README.md")
    assert "不要覆盖" in readme
    assert "API_SERVER_KEY" in readme
    assert "必须不同" in readme
    assert "location = /api/mcp { return 404; }" in readme
    assert "请检索今天最重要的三条Agent动态，整理好以后放进知流。" in readme


def test_operations_assets_preserve_data_and_hide_public_mcp() -> None:
    operations = read("docs/operations.md")
    backup = read("deploy/scripts/sqlite-backup.sh")
    restore = read("deploy/scripts/sqlite-restore.sh")
    acceptance = read("deploy/scripts/acceptance.sh")
    host_nginx = read("deploy/nginx-host.conf.example")

    assert "docker compose down -v" in operations
    assert "RESTORE_ZHILIU_SQLITE" in operations
    assert "/api/diagnostics" in operations
    assert "X-Request-ID" in operations
    assert "MCP最近写入" in operations
    assert "app.ops.sqlite_snapshot backup" in backup
    assert "sha256sum" in backup
    assert "app.ops.sqlite_snapshot verify" in backup
    assert "RESTORE_ZHILIU_SQLITE" in restore
    assert "pre-restore" in restore
    assert "docker compose stop backend" in restore
    assert "down -v" not in backup
    assert "down -v" not in restore
    assert "/api/diagnostics" in acceptance
    assert 'MCP_STATUS" != "401"' in acceptance
    assert 'PUBLIC_MCP_STATUS" != "404"' in acceptance
    assert host_nginx.index("location = /api/mcp") < host_nginx.index("location /")
    assert "--no-access-log" in read("backend/Dockerfile")
