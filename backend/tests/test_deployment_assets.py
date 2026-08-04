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
