"""Minimal HTTP client used by the orchestrator to call its 3 downstream MCPs.

The wire protocol is Anthropic MCP over HTTP. We use a simple JSON-RPC-style
POST to /mcp/tools/<name>/invoke. Failure cases bubble as UpstreamError.
"""

from __future__ import annotations

import os
from typing import Any

from grace_shared.errors import UpstreamError

DEFAULT_TIMEOUT_SECONDS = 30.0


class MCPClient:
    def __init__(
        self,
        base_url: str,
        bearer_token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: Any | None = None,
    ) -> None:
        if not base_url:
            raise RuntimeError("base_url required for MCPClient")
        self._base = base_url.rstrip("/")
        self._token = bearer_token
        self._timeout = timeout
        self._http_client = http_client

    async def call_tool(self, tool_name: str, params: dict) -> dict:
        client = self._http_client
        owns = False
        if client is None:
            import httpx  # type: ignore

            client = httpx.AsyncClient(timeout=self._timeout)
            owns = True
        try:
            url = f"{self._base}/mcp/tools/{tool_name}/invoke"
            try:
                resp = await client.post(
                    url,
                    json=params,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
            except Exception as exc:
                raise UpstreamError(f"{tool_name} request failed: {exc}") from exc
            if resp.status_code >= 400:
                raise UpstreamError(
                    f"{tool_name} HTTP {resp.status_code}: {resp.text[:200]}"
                )
            try:
                return resp.json()
            except Exception as exc:
                raise UpstreamError(f"{tool_name} non-JSON response") from exc
        finally:
            if owns:
                await client.aclose()


def get_required_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} env var is required")
    return v
