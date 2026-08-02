import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "GET", "DELETE"])
@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token-that-is-long-enough"])
async def test_mcp_rejects_missing_or_wrong_bearer(
    method: str,
    authorization: str | None,
) -> None:
    settings = Settings(
        scheduler_enabled=False,
        zhiliu_mcp_token="test-mcp-token-that-is-at-least-32-characters",
        _env_file=None,
    )
    app = create_app(start_background_scheduler=False, settings=settings)
    headers = {"Authorization": authorization} if authorization else {}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.request(method, "/api/mcp", headers=headers, json={})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "test-mcp-token" not in response.text


@pytest.mark.asyncio
async def test_mcp_auth_does_not_protect_regular_web_api() -> None:
    settings = Settings(
        scheduler_enabled=False,
        zhiliu_mcp_token="test-mcp-token-that-is-at-least-32-characters",
        _env_file=None,
    )
    app = create_app(start_background_scheduler=False, settings=settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
