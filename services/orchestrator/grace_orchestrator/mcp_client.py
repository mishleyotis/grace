"""JSON-RPC client used by the orchestrator to call its 3 downstream MCP services.

Wire protocol is the standard MCP Streamable HTTP transport. We POST a
JSON-RPC 2.0 ``tools/call`` request to ``<base>/mcp/`` (with both
``application/json`` and ``text/event-stream`` accepted, per MCP) and unpack
``result.structuredContent`` if present, falling back to the JSON-encoded
``result.content[0].text``.

Failure cases bubble as ``UpstreamError`` so the orchestrator can isolate
each tier.
"""

from __future__ import annotations

import json
import os
import uuid
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
        if not self._base.endswith("/mcp"):
            self._endpoint = f"{self._base}/mcp/"
        else:
            self._endpoint = self._base + "/"
        self._token = bearer_token
        self._timeout = timeout
        self._http_client = http_client

    async def call_tool(self, tool_name: str, params: dict) -> dict:
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": params},
        }
        client = self._http_client
        owns = False
        if client is None:
            import httpx  # type: ignore

            client = httpx.AsyncClient(timeout=self._timeout)
            owns = True
        try:
            try:
                resp = await client.post(
                    self._endpoint,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                    },
                )
            except Exception as exc:
                raise UpstreamError(f"{tool_name} request failed: {exc}") from exc
            if resp.status_code >= 400:
                raise UpstreamError(
                    f"{tool_name} HTTP {resp.status_code}: {resp.text[:200]}"
                )
            payload = _parse_response_body(resp)
        finally:
            if owns:
                await client.aclose()

        if "error" in payload:
            err = payload["error"]
            raise UpstreamError(
                f"{tool_name} JSON-RPC error: {err.get('message') or err}"
            )
        result = payload.get("result") or {}
        # MCP returns either structuredContent (preferred) or content[*].text
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        content = result.get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    return json.loads(item.get("text") or "")
                except Exception:
                    continue
        # Fall back to the raw result if neither shape applies
        return result


def _parse_response_body(resp: Any) -> dict:
    ctype = (resp.headers.get("content-type") or "").lower()
    text = resp.text
    if "text/event-stream" in ctype:
        # Each event is "event: message\ndata: <json>\n\n"
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if not payload:
                    continue
                try:
                    return json.loads(payload)
                except Exception:
                    continue
        raise UpstreamError("no parsable data event in SSE response")
    try:
        return resp.json()
    except Exception as exc:
        raise UpstreamError(f"non-JSON MCP response: {exc}") from exc


def get_required_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} env var is required")
    return v
