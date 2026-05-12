"""Tool implementations for grace-site-mirror.

Five tools:
  - site_mirror_get_section(name)
  - site_mirror_search(query, limit=10)
  - site_mirror_get_url_index()
  - site_mirror_get_nav_map()
  - site_mirror_get_page_links(page_name)

Every response is run through ``_scrub_urls`` so the mirror doc ID and Apps
Script prefix never leak to the Skill / user.
"""

from __future__ import annotations

from typing import Any

from grace_shared.errors import GraceError, ValidationError, to_error_dict
from grace_shared.url_canon import (
    canonicalize_zennify_url,
    looks_like_internal_url,
)

from grace_site_mirror.client import MAX_SEARCH_LIMIT, AppsScriptClient


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _scrub_item_urls(item: dict, *, site_url: str = "") -> dict:
    out = dict(item)
    fallback = site_url or _safe_str(item.get("siteUrl"))
    if "url" in out:
        out["url"] = canonicalize_zennify_url(_safe_str(out.get("url")), fallback)
    if "siteUrl" in out:
        out["siteUrl"] = canonicalize_zennify_url(
            _safe_str(out.get("siteUrl")), fallback
        )
    return out


def _scrub_results_list(items: list) -> list[dict]:
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        scrubbed = _scrub_item_urls(item)
        out.append(scrubbed)
    return out


def _scrub_links_list(items: list, *, fallback_site_url: str = "") -> list[dict]:
    """For page-links: drop any link whose URL is internal (mirror doc or Apps Script).

    Per SM-S5: 'the mirror-doc link is dropped from the links array (not just
    rewritten); only canonical / external URLs remain'.
    """
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = _safe_str(item.get("url"))
        if looks_like_internal_url(url):
            continue
        out.append({**item, "url": url})
    return out


async def site_mirror_get_section(client: AppsScriptClient, name: str) -> dict:
    if not isinstance(name, str) or not name.strip():
        return to_error_dict(ValidationError("name is required"))
    try:
        data = await client.call("getSection", {"name": name})
    except GraceError as exc:
        return to_error_dict(exc)
    if not isinstance(data, dict):
        return to_error_dict(ValidationError("unexpected response shape"))
    if data.get("status") == "no_results":
        return {"status": "no_results", "name": name}
    site_url = _safe_str(data.get("siteUrl"))
    return {
        "status": "ok",
        "siteUrl": canonicalize_zennify_url(site_url, site_url),
        "name": _safe_str(data.get("name")) or name,
        "content": _safe_str(data.get("content")),
        "paragraphs": data.get("paragraphs") or [],
    }


async def site_mirror_search(
    client: AppsScriptClient, query: str, limit: int = 10
) -> dict:
    if not isinstance(query, str) or not query.strip():
        return to_error_dict(ValidationError("query is required"))
    # Silent clamp per SM-S6
    if not isinstance(limit, int) or limit < 1:
        limit = 10
    limit = min(limit, MAX_SEARCH_LIMIT)
    try:
        data = await client.call("searchSections", {"query": query, "limit": limit})
    except GraceError as exc:
        return to_error_dict(exc)
    results_in = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results_in, list):
        results_in = []
    results = _scrub_results_list(results_in)[:limit]
    if not results:
        return {"status": "no_results", "query": query}
    return {"status": "ok", "query": query, "results": results}


async def site_mirror_get_url_index(client: AppsScriptClient) -> dict:
    try:
        data = await client.call("getURLIndex")
    except GraceError as exc:
        return to_error_dict(exc)
    pages_in = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages_in, list):
        pages_in = []
    pages = _scrub_results_list(pages_in)
    return {"status": "ok", "pages": pages}


async def site_mirror_get_nav_map(client: AppsScriptClient) -> dict:
    try:
        data = await client.call("getNavMap")
    except GraceError as exc:
        return to_error_dict(exc)
    nav = data.get("nav") if isinstance(data, dict) else None
    return {"status": "ok", "nav": _scrub_nav(nav)}


def _scrub_nav(node: Any) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in ("siteUrl", "url"):
                out[k] = canonicalize_zennify_url(_safe_str(v), _safe_str(v))
            else:
                out[k] = _scrub_nav(v)
        return out
    if isinstance(node, list):
        return [_scrub_nav(x) for x in node]
    return node


async def site_mirror_get_page_links(client: AppsScriptClient, page_name: str) -> dict:
    if not isinstance(page_name, str) or not page_name.strip():
        return to_error_dict(ValidationError("page_name is required"))
    try:
        data = await client.call("getLinkIndex", {"name": page_name})
    except GraceError as exc:
        return to_error_dict(exc)
    links_in = data.get("links") if isinstance(data, dict) else None
    if not isinstance(links_in, list):
        links_in = []
    links = _scrub_links_list(links_in)
    return {"status": "ok", "page_name": page_name, "links": links}
