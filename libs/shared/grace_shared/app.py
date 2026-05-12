"""ASGI app builder: wraps a FastMCP instance with bearer auth + /healthz + access logging.

Importing fastmcp/starlette is deferred so unit tests can exercise pure logic
without those deps installed.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable

from grace_shared.config import ServiceConfig

logger = logging.getLogger("grace")


def _json_response(status_code: int, payload: dict) -> Any:
    from starlette.responses import JSONResponse  # type: ignore

    return JSONResponse(payload, status_code=status_code)


class BearerAuthMiddleware:
    """Reject any /mcp/* request without a matching bearer token."""

    def __init__(self, app: Any, *, expected_token: str, service: str) -> None:
        self.app = app
        self._expected = expected_token
        self._service = service

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        prefix = "Bearer "
        reason = None
        if not auth:
            reason = "missing"
        elif not auth.startswith(prefix):
            reason = "malformed"
        else:
            token = auth[len(prefix) :].strip()
            if token != self._expected:
                reason = "mismatch"
        if reason is not None:
            logger.warning(
                json.dumps(
                    {
                        "service": self._service,
                        "message": "invalid_bearer_token",
                        "path": path,
                        "reason": reason,
                    }
                )
            )
            await _send_plain(send, 401, b"")
            return
        await self.app(scope, receive, send)


class AccessLogMiddleware:
    def __init__(self, app: Any, *, service: str) -> None:
        self.app = app
        self._service = service

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.monotonic()
        status_holder: dict[str, int] = {"code": 0}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                json.dumps(
                    {
                        "service": self._service,
                        "method": scope.get("method", ""),
                        "path": scope.get("path", ""),
                        "status_code": status_holder["code"],
                        "latency_ms": latency_ms,
                    }
                )
            )


async def _send_plain(send: Callable, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def build_healthz(service_name: str) -> Callable[..., Awaitable[Any]]:
    async def healthz(_request: Any) -> Any:
        return _json_response(200, {"status": "ok", "service": service_name})

    return healthz


def build_app(mcp: Any, *, name: str, config: ServiceConfig) -> Any:
    """Wrap a FastMCP instance into a Starlette ASGI app with auth + healthz + logging."""
    from starlette.applications import Starlette  # type: ignore
    from starlette.routing import Mount, Route  # type: ignore

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(message)s",
    )

    mcp_app = mcp.http_app() if hasattr(mcp, "http_app") else mcp.streamable_http_app()
    routes = [
        Route("/healthz", build_healthz(name)),
        Mount("/mcp", app=mcp_app),
    ]
    app = Starlette(routes=routes, lifespan=getattr(mcp_app, "lifespan", None))
    app = BearerAuthMiddleware(app, expected_token=config.bearer_token, service=name)
    app = AccessLogMiddleware(app, service=name)
    return app
