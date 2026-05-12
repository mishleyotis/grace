"""FastMCP server entry point for grace-site-mirror."""

from __future__ import annotations

from grace_shared.app import build_app
from grace_shared.config import ServiceConfig

from grace_site_mirror import tools
from grace_site_mirror.client import AppsScriptClient, get_endpoint_from_env

SERVICE_NAME = "grace-site-mirror"


def create_app():  # pragma: no cover - exercised in deploy, not unit tests
    from fastmcp import FastMCP  # type: ignore

    config = ServiceConfig.from_env(SERVICE_NAME)
    client = AppsScriptClient(get_endpoint_from_env())

    mcp = FastMCP(SERVICE_NAME)

    @mcp.tool()
    async def site_mirror_get_section(name: str) -> dict:
        return await tools.site_mirror_get_section(client, name)

    @mcp.tool()
    async def site_mirror_search(query: str, limit: int = 10) -> dict:
        return await tools.site_mirror_search(client, query, limit)

    @mcp.tool()
    async def site_mirror_get_url_index() -> dict:
        return await tools.site_mirror_get_url_index(client)

    @mcp.tool()
    async def site_mirror_get_nav_map() -> dict:
        return await tools.site_mirror_get_nav_map(client)

    @mcp.tool()
    async def site_mirror_get_page_links(page_name: str) -> dict:
        return await tools.site_mirror_get_page_links(client, page_name)

    return build_app(mcp, name=SERVICE_NAME, config=config)


app = None  # populated when run under uvicorn

if __name__ == "__main__":  # pragma: no cover
    import os

    import uvicorn  # type: ignore

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
