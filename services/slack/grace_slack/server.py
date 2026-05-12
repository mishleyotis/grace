"""FastMCP server entry point for grace-slack."""

from __future__ import annotations

from grace_shared.app import build_app
from grace_shared.config import ServiceConfig

from grace_slack import DEFAULT_DAYS_BACK, DEFAULT_LIMIT, tools
from grace_slack.client import build_default_client

SERVICE_NAME = "grace-slack"


def create_app():  # pragma: no cover - exercised at deploy
    from fastmcp import FastMCP  # type: ignore

    config = ServiceConfig.from_env(SERVICE_NAME)
    client = build_default_client()

    mcp = FastMCP(SERVICE_NAME)

    @mcp.tool()
    async def slack_search_pmo(
        query: str,
        days_back: int = DEFAULT_DAYS_BACK,
        limit: int = DEFAULT_LIMIT,
        authoritative_only: bool = True,
    ) -> dict:
        return tools.search_pmo(
            client,
            query,
            days_back=days_back,
            limit=limit,
            authoritative_only=authoritative_only,
        )

    @mcp.tool()
    async def slack_get_thread(thread_ts: str, limit: int = 100) -> dict:
        return tools.get_thread(client, thread_ts, limit=limit)

    return build_app(mcp, name=SERVICE_NAME, config=config)


if __name__ == "__main__":  # pragma: no cover
    import os

    import uvicorn  # type: ignore

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
