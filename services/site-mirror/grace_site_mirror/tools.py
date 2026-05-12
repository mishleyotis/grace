"""Tool implementations for grace-site-mirror.

Five tools:
  - site_mirror_get_section(name)
  - site_mirror_search(query, limit=10)
  - site_mirror_get_url_index()
  - site_mirror_get_nav_map()
  - site_mirror_get_page_links(page_name)

Every response is run through ``_scrub_urls`` so the mirror doc ID and Apps
Script prefix never leak to the Skill / user.

API-compatibility notes (live SiteMirrorQuery web app):
  - searchSections expects ``q=`` (the design's spec said ``query=``); we
    send both for forward/back compatibility.
  - getURLIndex returns ``sections``, not ``pages``; each item has
    ``pageName`` (we map to ``name``). The response also includes a
    top-level ``mirrorDocId`` field which is scrubbed before return.
  - All actions tolerate either the design's response shape or the real
    one; the tool output is the design's canonical shape.
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


def _normalize_item(item: dict) -> dict:
    """Map Apps Script keys to the design's canonical names."""
    out = dict(item)
    if "name" not in out and "pageName" in out:
        out["name"] = out["pageName"]
    if "paragraph_bounds" not in out and ("paraStart" in out or "paraEnd" in out):
        out["paragraph_bounds"] = {
            "start": out.get("paraStart"),
            "end": out.get("paraEnd"),
        }
    return out


def _scrub_item_urls(item: dict, *, site_url: str = "") -> dict:
    out = _normalize_item(item)
    fallback = site_url or _safe_str(out.get("siteUrl"))
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


def _pick_array(data: dict, *keys: str) -> list:
    """Return the first array field present among ``keys``; else []."""
    for k in keys:
        v = data.get(k)
        if isinstance(v, list):
            return v
    return []


async def site_mirror_get_section(client: AppsScriptClient, name: str) -> dict:
    if not isinstance(name, str) or not name.strip():
        return to_error_dict(ValidationError("name is required"))
    try:
        data = await client.call("getSection", {"name": name})
    except GraceError as exc:
        return to_error_dict(exc)
    if not isinstance(data, dict):
        return to_error_dict(ValidationError("unexpected response shape"))
    if data.get("status") == "no_results" or data.get("error"):
        out: dict = {"status": "no_results", "name": name}
        sug = data.get("suggestions")
        if isinstance(sug, list) and sug:
            out["suggestions"] = sug
        return out
    site_url = _safe_str(data.get("siteUrl"))
    content = (
        _safe_str(data.get("content"))
        or _safe_str(data.get("text"))
        or _safe_str(data.get("body"))
    )
    paragraphs = data.get("paragraphs") or data.get("paragraphsText") or []
    return {
        "status": "ok",
        "siteUrl": canonicalize_zennify_url(site_url, site_url),
        "name": _safe_str(data.get("name")) or _safe_str(data.get("pageName")) or name,
        "content": content,
        "paragraphs": paragraphs if isinstance(paragraphs, list) else [],
        # Live script extras (pass through when present, omit otherwise)
        **(
            {"page_structure": data["pageStructure"]}
            if isinstance(data.get("pageStructure"), list)
            else {}
        ),
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
    # Apps Script uses `q`; we send both for compatibility with older deploys.
    try:
        data = await client.call(
            "searchSections", {"q": query, "query": query, "limit": limit}
        )
    except GraceError as exc:
        return to_error_dict(exc)
    if not isinstance(data, dict):
        return to_error_dict(ValidationError("unexpected response shape"))
    if data.get("error"):
        return {"status": "no_results", "query": query, "warning": _safe_str(data.get("error"))}
    results_in = _pick_array(data, "results", "matches", "sections", "pages")
    results = _scrub_results_list(results_in)[:limit]
    if not results:
        return {"status": "no_results", "query": query}
    out: dict = {"status": "ok", "query": query, "results": results}
    # Surface the script's query normalization (it expands SOW->Statement of
    # Work etc.) so the Skill can show what was actually searched.
    qn = _safe_str(data.get("queryNormalized"))
    if qn and qn != query:
        out["query_normalized"] = qn
    return out


async def site_mirror_get_url_index(client: AppsScriptClient) -> dict:
    try:
        data = await client.call("getURLIndex")
    except GraceError as exc:
        return to_error_dict(exc)
    if not isinstance(data, dict):
        return to_error_dict(ValidationError("unexpected response shape"))
    pages_in = _pick_array(data, "sections", "pages")
    pages = _scrub_results_list(pages_in)
    return {"status": "ok", "pages": pages}


async def site_mirror_get_nav_map(client: AppsScriptClient) -> dict:
    try:
        data = await client.call("getNavMap")
    except GraceError as exc:
        return to_error_dict(exc)
    if not isinstance(data, dict):
        return to_error_dict(ValidationError("unexpected response shape"))
    # Real script returns `entries: [{text, siteUrl}]` (a flat list).
    # Design spec assumed a nested `nav` tree. Accept either.
    if isinstance(data.get("entries"), list):
        entries = []
        for it in data["entries"]:
            if not isinstance(it, dict):
                continue
            entries.append(
                {
                    "text": _safe_str(it.get("text")),
                    "siteUrl": canonicalize_zennify_url(
                        _safe_str(it.get("siteUrl")), _safe_str(it.get("siteUrl"))
                    ),
                }
            )
        return {"status": "ok", "entries": entries}
    nav = data.get("nav") or data.get("navMap") or data.get("tree")
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
    # Real script requires `page=`; design spec used `name=`. Send both.
    try:
        data = await client.call(
            "getLinkIndex", {"page": page_name, "name": page_name}
        )
    except GraceError as exc:
        return to_error_dict(exc)
    if not isinstance(data, dict):
        return to_error_dict(ValidationError("unexpected response shape"))
    if data.get("error"):
        return {
            "status": "no_results",
            "page_name": page_name,
            "warning": _safe_str(data.get("error")),
        }
    links_in = _pick_array(data, "links", "results")
    links = _scrub_links_list(links_in)
    return {"status": "ok", "page_name": page_name, "links": links}
