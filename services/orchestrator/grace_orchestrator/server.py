"""FastMCP server entry point for grace-orchestrator."""

from __future__ import annotations

from grace_shared.app import build_app
from grace_shared.config import ServiceConfig

from grace_orchestrator import DEFAULT_PER_TIER_LIMIT
from grace_orchestrator.bundle import retrieve_bundle
from grace_orchestrator.mcp_client import MCPClient, get_required_env

SERVICE_NAME = "grace-orchestrator"


def create_app():  # pragma: no cover
    from fastmcp import FastMCP  # type: ignore

    config = ServiceConfig.from_env(SERVICE_NAME)

    site_mirror = MCPClient(
        get_required_env("SITE_MIRROR_URL"), config.bearer_token
    )
    sheets = MCPClient(get_required_env("SHEETS_URL"), config.bearer_token)
    slack = MCPClient(get_required_env("SLACK_URL"), config.bearer_token)

    async def site_mirror_search(query: str, limit: int) -> dict:
        return await site_mirror.call_tool(
            "site_mirror_search", {"query": query, "limit": limit}
        )

    async def drive_map_search(query: str, limit: int) -> dict:
        return await sheets.call_tool(
            "drive_map_search", {"query": query, "limit": limit}
        )

    async def slack_search_pmo(query: str, limit: int, auth_only: bool) -> dict:
        return await slack.call_tool(
            "slack_search_pmo",
            {"query": query, "limit": limit, "authoritative_only": auth_only},
        )

    mcp = FastMCP(SERVICE_NAME)

    @mcp.tool()
    async def pmo_retrieve_grounding_bundle(
        query: str,
        practice_area: str = "",
        sender_email: str = "",
        slack_authoritative_only: bool = True,
        per_tier_limit: int = DEFAULT_PER_TIER_LIMIT,
    ) -> dict:
        return await retrieve_bundle(
            query=query,
            site_mirror_search=site_mirror_search,
            drive_map_search=drive_map_search,
            slack_search_pmo=slack_search_pmo,
            practice_area=practice_area,
            sender_email=sender_email,
            slack_authoritative_only=slack_authoritative_only,
            per_tier_limit=per_tier_limit,
        )

    return build_app(mcp, name=SERVICE_NAME, config=config)


if __name__ == "__main__":  # pragma: no cover
    import os

    import uvicorn  # type: ignore

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
