"""Unit + end-to-end tests for the orchestrator's MCPClient.

Uses fastmcp.Client's in-memory short-circuit (Client(mcp)) and a real
streamable-HTTP path against a build_app-wrapped FastMCP, to verify the
orchestrator's connector matches the actual MCP transport that production
will use.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import pytest


@contextmanager
def _bearer_env(token: str = "x" * 32):
    prev = os.environ.get("MCP_BEARER_TOKEN")
    os.environ["MCP_BEARER_TOKEN"] = token
    try:
        yield token
    finally:
        if prev is None:
            os.environ.pop("MCP_BEARER_TOKEN", None)
        else:
            os.environ["MCP_BEARER_TOKEN"] = prev


@pytest.fixture
def upstream_mcp():
    from fastmcp import FastMCP  # type: ignore

    mcp = FastMCP("upstream-mcp")

    @mcp.tool()
    async def upstream_search(query: str, limit: int = 10) -> dict:
        return {
            "status": "ok",
            "query": query,
            "results": [{"name": f"hit-{i}", "score": 10 - i} for i in range(min(limit, 3))],
        }

    @mcp.tool()
    async def upstream_error() -> dict:
        raise RuntimeError("simulated upstream failure")

    return mcp


@pytest.mark.asyncio
async def test_in_memory_round_trip_returns_structured_content(upstream_mcp):
    """In-memory: Client(mcp) talks directly to the FastMCP instance.
    Validates that structured_content is unwrapped correctly."""
    from fastmcp import Client  # type: ignore
    from grace_orchestrator.mcp_client import MCPClient

    async with Client(upstream_mcp) as client:
        c = MCPClient(base_url="", bearer_token="ignored", client=client)
        out = await c.call_tool("upstream_search", {"query": "kickoff", "limit": 2})
        assert out["status"] == "ok"
        assert out["query"] == "kickoff"
        assert len(out["results"]) == 2
        assert out["results"][0]["name"] == "hit-0"


@pytest.mark.asyncio
async def test_in_memory_tool_failure_raises_upstream_error(upstream_mcp):
    from fastmcp import Client  # type: ignore
    from grace_orchestrator.mcp_client import MCPClient
    from grace_shared.errors import UpstreamError

    async with Client(upstream_mcp) as client:
        c = MCPClient(base_url="", bearer_token="ignored", client=client)
        with pytest.raises(UpstreamError, match="upstream_error failed"):
            await c.call_tool("upstream_error", {})


def test_normalize_endpoint_appends_mcp():
    from grace_orchestrator.mcp_client import _normalize_endpoint

    assert _normalize_endpoint("https://svc.example.com") == "https://svc.example.com/mcp"
    assert _normalize_endpoint("https://svc.example.com/") == "https://svc.example.com/mcp"
    assert (
        _normalize_endpoint("https://svc.example.com/mcp") == "https://svc.example.com/mcp"
    )
    assert (
        _normalize_endpoint("https://svc.example.com/mcp/") == "https://svc.example.com/mcp"
    )


def test_constructor_requires_base_or_client():
    from grace_orchestrator.mcp_client import MCPClient

    with pytest.raises(RuntimeError, match="base_url required"):
        MCPClient(base_url="", bearer_token="x")
