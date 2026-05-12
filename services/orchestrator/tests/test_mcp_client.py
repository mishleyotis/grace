"""Unit tests for the JSON-RPC MCPClient used by the orchestrator."""

from __future__ import annotations

import json

import pytest
from grace_orchestrator.mcp_client import MCPClient


class FakeResp:
    def __init__(self, status_code=200, headers=None, body=None, text=""):
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self._body = body
        if text:
            self.text = text
        elif body is not None:
            self.text = json.dumps(body)
        else:
            self.text = ""

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    async def post(self, url, json=None, headers=None):  # noqa: A002
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.resp

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_structured_content_unwrapped():
    body = {"jsonrpc": "2.0", "id": "x", "result": {"structuredContent": {"status": "ok", "results": [1]}}}
    http = FakeHttp(FakeResp(body=body))
    client = MCPClient("https://svc-abc.run.app", "tok", http_client=http)
    out = await client.call_tool("foo", {"q": "x"})
    assert out == {"status": "ok", "results": [1]}
    # Endpoint normalization
    assert http.calls[0]["url"].endswith("/mcp/")
    # JSON-RPC envelope
    assert http.calls[0]["json"]["method"] == "tools/call"
    assert http.calls[0]["json"]["params"]["name"] == "foo"
    assert http.calls[0]["json"]["params"]["arguments"] == {"q": "x"}
    # Bearer header
    assert http.calls[0]["headers"]["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_text_content_fallback():
    payload = {"status": "ok", "results": []}
    body = {
        "jsonrpc": "2.0",
        "id": "x",
        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }
    http = FakeHttp(FakeResp(body=body))
    client = MCPClient("https://svc/mcp", "tok", http_client=http)
    assert await client.call_tool("foo", {}) == payload


@pytest.mark.asyncio
async def test_sse_response_parsed():
    payload = {"jsonrpc": "2.0", "id": "1", "result": {"structuredContent": {"x": 1}}}
    text = f"event: message\ndata: {json.dumps(payload)}\n\n"
    resp = FakeResp(headers={"content-type": "text/event-stream"}, text=text)
    http = FakeHttp(resp)
    client = MCPClient("https://svc", "tok", http_client=http)
    assert await client.call_tool("foo", {}) == {"x": 1}


@pytest.mark.asyncio
async def test_jsonrpc_error_raises_upstream():
    body = {"jsonrpc": "2.0", "id": "x", "error": {"code": -32600, "message": "bad"}}
    http = FakeHttp(FakeResp(body=body))
    client = MCPClient("https://svc", "tok", http_client=http)
    with pytest.raises(Exception, match="JSON-RPC error: bad"):
        await client.call_tool("foo", {})


@pytest.mark.asyncio
async def test_http_5xx_raises_upstream():
    resp = FakeResp(status_code=500, text="boom", body=None)
    http = FakeHttp(resp)
    client = MCPClient("https://svc", "tok", http_client=http)
    with pytest.raises(Exception, match="HTTP 500"):
        await client.call_tool("foo", {})
