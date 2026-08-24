import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("zhiliu.request")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")


class SafeRequestLogMiddleware:
    """Log request metadata without query strings, headers, or bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied_id = next(
            (value.decode("ascii", errors="ignore") for key, value in scope.get("headers", []) if key.lower() == b"x-request-id"),
            "",
        )
        request_id = supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else uuid4().hex
        started = perf_counter()
        response_status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(
                "request_failed request_id=%s method=%s path=%s duration_ms=%d",
                request_id,
                scope.get("method", ""),
                scope.get("path", ""),
                round((perf_counter() - started) * 1000),
            )
            raise
        else:
            logger.info(
                "request_complete request_id=%s method=%s path=%s status=%d duration_ms=%d",
                request_id,
                scope.get("method", ""),
                scope.get("path", ""),
                response_status,
                round((perf_counter() - started) * 1000),
            )
