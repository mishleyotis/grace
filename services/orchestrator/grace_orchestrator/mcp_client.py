"""Inter-MCP client used by the orchestrator.

Wraps ``fastmcp.Client`` to make typed JSON tool calls against downstream
grace MCP services. ``fastmcp.Client`` handles the full MCP handshake
(initialize, session ID negotiation, ``notifications/initialized``), the
streamable-HTTP transport, and SSE response framing — we just need to
hand it a URL + bearer token and call ``call_tool``.

Failure cases bubble as ``UpstreamError`` so the orchestrator's
per-tier failure isolation can mark the tier as ``error: ...`` and still
return results from the other tiers.
"""

from __future__ import annotations

import json
import os
from typing import Any

from grace_shared.errors import UpstreamError

DEFAULT_TIMEOUT_SECONDS = 30.0


def _normalize_endpoint(base_url: str) -> str:
    """Return the canonical ``<base>/mcp`` URL used by FastMCP's streamable-HTTP transport."""
    b = base_url.rstrip("/")
    if b.endswith("/mcp"):
        return b
    return f"{b}/mcp"


class MCPClient:
    """JSON-tool client over MCP streamable-HTTP transport.

    Used by the orchestrator to call grace-site-mirror / grace-sheets /
    grace-slack. Each ``call_tool`` opens a session, runs the handshake,
    calls the tool, and closes the session. That's deliberate: each
    request is independent, sessions never leak between tools, and a
    failure on one call doesn't poison the next.
    """

    def __init__(
        self,
        base_url: str,
        bearer_token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        # Test seam: a pre-built fastmcp.Client to reuse instead of building
        # one per call. When provided, base_url/bearer/timeout are ignored.
        client: Any | None = None,
    ) -> None:
        if not base_url and client is None:
            raise RuntimeError("base_url required for MCPClient")
        self._endpoint = _normalize_endpoint(base_url) if base_url else ""
        self._token = bearer_token
        self._timeout = timeout
        self._client = client

    async def call_tool(self, tool_name: str, params: dict) -> dict:
        if self._client is not None:
            return await self._call_with(self._client, tool_name, params)

        from fastmcp import Client  # type: ignore

        async with Client(
            self._endpoint,
            auth=self._token,
            timeout=self._timeout,
            client_info={"name": "grace-orchestrator", "version": "1.0.0"},
        ) as client:
            return await self._call_with(client, tool_name, params)

    @staticmethod
    async def _call_with(client: Any, tool_name: str, params: dict) -> dict:
        try:
            result = await client.call_tool(tool_name, params)
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"{tool_name} failed: {exc}") from exc

        # FastMCP returns a CallToolResult-like object. Prefer
        # structuredContent (canonical JSON), fall back to content[0].text.
        sc = getattr(result, "structured_content", None) or getattr(
            result, "structuredContent", None
        )
        if isinstance(sc, dict):
            # FastMCP sometimes wraps non-object returns as {"result": <value>}
            if "result" in sc and len(sc) == 1 and isinstance(sc["result"], dict):
                return sc["result"]
            return sc

        content = getattr(result, "content", None) or []
        for item in content:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text")
            if not text:
                continue
            try:
                return json.loads(text)
            except Exception:
                continue

        # Last-resort: data attribute (some FastMCP versions)
        data = getattr(result, "data", None)
        if isinstance(data, dict):
            return data

        raise UpstreamError(f"{tool_name} returned no parsable JSON content")


def get_required_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} env var is required")
    return v


__all__ = ["MCPClient", "get_required_env", "DEFAULT_TIMEOUT_SECONDS"]
