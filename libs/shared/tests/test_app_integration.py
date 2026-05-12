"""End-to-end ASGI integration test for grace_shared.app.build_app.

Spins up a real FastMCP instance with a tool, wraps it via build_app,
and hits it through Starlette's TestClient. This catches the kind of
routing bug a pure-unit test misses — the one where /healthz is shadowed
or /mcp/ returns 404 because of double-mounting.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def app_with_bearer(monkeypatch):
    """Build the real ASGI app using FastMCP + build_app, returning (app, bearer_token)."""
    bearer = "a" * 32
    monkeypatch.setenv("MCP_BEARER_TOKEN", bearer)

    from fastmcp import FastMCP  # type: ignore
    from grace_shared.app import build_app
    from grace_shared.config import ServiceConfig

    mcp = FastMCP("grace-test")

    @mcp.tool()
    async def echo(msg: str) -> dict:
        return {"echo": msg}

    config = ServiceConfig.from_env("grace-test")
    app = build_app(mcp, name="grace-test", config=config)
    return app, bearer


def test_healthz_returns_200_with_service_name(app_with_bearer):
    """GET /healthz is reachable with no bearer and returns the service name."""
    from starlette.testclient import TestClient

    app, _ = app_with_bearer
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "grace-test"


def test_healthz_does_not_require_bearer(app_with_bearer):
    """The bearer middleware must not gate /healthz."""
    from starlette.testclient import TestClient

    app, _ = app_with_bearer
    with TestClient(app) as c:
        r = c.get("/healthz", headers={"Authorization": "Bearer wrong-token"})
        # Even a wrong bearer is OK on /healthz (the middleware only gates /mcp/*).
        assert r.status_code == 200


def test_mcp_path_without_bearer_returns_401(app_with_bearer):
    """POST /mcp without bearer → 401 (BearerAuthMiddleware fires)."""
    from starlette.testclient import TestClient

    app, _ = app_with_bearer
    with TestClient(app) as c:
        r = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert r.status_code == 401


def test_mcp_path_with_wrong_bearer_returns_401(app_with_bearer):
    from starlette.testclient import TestClient

    app, _ = app_with_bearer
    with TestClient(app) as c:
        r = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list"},
            headers={
                "Authorization": "Bearer not-the-token",
                "Accept": "application/json, text/event-stream",
            },
        )
        assert r.status_code == 401


def test_mcp_path_with_correct_bearer_reaches_handler(app_with_bearer):
    """POST /mcp with correct bearer must reach FastMCP's handler.

    Without an MCP initialize handshake the handler returns a JSON-RPC 400
    with 'Missing session ID' — that's *fine*. The point of this test is
    to prove the request travels Auth → AccessLog → FastMCP and is not
    intercepted by a 404.
    """
    from starlette.testclient import TestClient

    app, bearer = app_with_bearer
    with TestClient(app) as c:
        r = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list"},
            headers={
                "Authorization": f"Bearer {bearer}",
                "Accept": "application/json, text/event-stream",
            },
        )
        # 400 = FastMCP handler ran and rejected because no session.
        # 200 = FastMCP handled (less common without initialize).
        # The wrong answer here is 404 (route missing) or 401 (auth bug).
        assert r.status_code in (200, 400), (
            f"expected 200/400, got {r.status_code}: {r.text[:300]}"
        )
        assert r.status_code != 404
        assert r.status_code != 401


def test_mcp_path_with_trailing_slash_also_works(app_with_bearer):
    """POST /mcp/ (with trailing slash) must NOT 404; FastMCP/Starlette
    handle either form."""
    from starlette.testclient import TestClient

    app, bearer = app_with_bearer
    with TestClient(app) as c:
        r = c.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list"},
            headers={
                "Authorization": f"Bearer {bearer}",
                "Accept": "application/json, text/event-stream",
            },
        )
        assert r.status_code != 404, r.text[:300]


def test_random_path_returns_404(app_with_bearer):
    """A completely unrelated path returns 404 from the inner app, not 200."""
    from starlette.testclient import TestClient

    app, _ = app_with_bearer
    with TestClient(app) as c:
        r = c.get("/this-path-does-not-exist")
        assert r.status_code == 404


def test_bearer_middleware_logs_reason_on_missing(app_with_bearer, caplog):
    """Auth failures emit structured log events for the metric to count."""
    import logging

    from starlette.testclient import TestClient

    app, _ = app_with_bearer
    with caplog.at_level(logging.WARNING, logger="grace"):
        with TestClient(app) as c:
            c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "1", "method": "tools/list"},
                headers={"Accept": "application/json, text/event-stream"},
            )
    assert any("invalid_bearer_token" in rec.message for rec in caplog.records)
