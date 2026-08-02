import json
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send


class StaticBearerAuth:
    def __init__(self, app: ASGIApp, token: str, path: str = "/api/mcp") -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") != self.path:
            body = b'{"detail":"Not Found"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"")
        if not secrets.compare_digest(supplied, self.expected):
            body = json.dumps({"detail": "MCP未授权"}, ensure_ascii=False).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"www-authenticate", b"Bearer"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
