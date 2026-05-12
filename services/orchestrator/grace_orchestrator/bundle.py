"""Parallel fan-out across the 3 retrieval tiers and bundle assembly."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from grace_shared.errors import ValidationError, to_error_dict

from grace_orchestrator import DEFAULT_PER_TIER_LIMIT, MAX_PER_TIER_LIMIT, ranking
from grace_orchestrator.dedup import dedup

# Each retriever is an async callable: (query, per_tier_limit) -> dict-from-mcp-tool
Retriever = Callable[[str, int], Awaitable[dict]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tier_status_from_payload(payload: dict | BaseException) -> tuple[str, list[dict]]:
    if isinstance(payload, BaseException):
        return f"error: {type(payload).__name__}", []
    if not isinstance(payload, dict):
        return "error: bad-payload", []
    if "error" in payload:
        return f"error: {payload['error']}", []
    status = payload.get("status") or ""
    results = payload.get("results") or payload.get("pages") or []
    if not isinstance(results, list):
        results = []
    if status == "no_results" or not results:
        return "no_results", []
    return "ok", results


def _grounding_block(query: str, tiers: dict, top_evidence: list[dict], iso_at: str) -> str:
    lines: list[str] = [f"**Grounding** — `{query}` — retrieved {iso_at}"]
    for tier_key, label in (
        ("site_mirror", "Tier 1 (Site Mirror)"),
        ("drive_map", "Tier 2 (Drive Map)"),
        ("slack", "Tier 3 (Slack)"),
    ):
        info = tiers.get(tier_key, {})
        status = info.get("status", "unknown")
        hits = len(info.get("results") or [])
        lines.append(f"- {label}: {status} ({hits} hits)")
    if top_evidence:
        lines.append("")
        lines.append("**Top evidence**:")
        for item in top_evidence[:5]:
            tiers_present = item.get("tiers_present") or [item.get("tier", "?")]
            tiers_str = ",".join(tiers_present)
            title = item.get("title") or item.get("url") or "(no title)"
            url = item.get("url") or ""
            score = int(item.get("score") or 0)
            if url:
                lines.append(f"- `{tiers_str}` [{title}]({url}) — score {score}")
            else:
                lines.append(f"- `{tiers_str}` {title} — score {score}")
    return "\n".join(lines)


async def retrieve_bundle(
    *,
    query: Any,
    site_mirror_search: Retriever,
    drive_map_search: Retriever,
    slack_search_pmo: Callable[[str, int, bool], Awaitable[dict]],
    practice_area: str = "",
    sender_email: str = "",
    slack_authoritative_only: bool = True,
    per_tier_limit: Any = DEFAULT_PER_TIER_LIMIT,
) -> dict:
    if not isinstance(query, str) or not query.strip():
        return to_error_dict(ValidationError("query is required"))
    try:
        limit = int(per_tier_limit)
    except Exception:
        limit = DEFAULT_PER_TIER_LIMIT
    if limit < 1:
        limit = DEFAULT_PER_TIER_LIMIT
    limit = min(limit, MAX_PER_TIER_LIMIT)

    results = await asyncio.gather(
        site_mirror_search(query, limit),
        drive_map_search(query, limit),
        slack_search_pmo(query, limit, slack_authoritative_only),
        return_exceptions=True,
    )

    sm_payload, dm_payload, sl_payload = results

    sm_status, sm_items = _tier_status_from_payload(sm_payload)
    dm_status, dm_items = _tier_status_from_payload(dm_payload)
    sl_status, sl_items = _tier_status_from_payload(sl_payload)

    sm_norm = ranking.normalize_site_mirror_items(sm_items)
    dm_norm = ranking.normalize_drive_map_items(dm_items)
    sl_norm = ranking.normalize_slack_items(
        sl_items, default_authoritative_only=slack_authoritative_only
    )

    combined = sm_norm + dm_norm + sl_norm
    deduped = dedup(combined)
    deduped.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
    # Assign final rank
    for i, item in enumerate(deduped, start=1):
        item["rank"] = i

    tiers = {
        "site_mirror": {"status": sm_status, "results": sm_items},
        "drive_map": {"status": dm_status, "results": dm_items},
        "slack": {"status": sl_status, "results": sl_items},
    }

    any_results = bool(deduped)
    iso_at = _now_iso()
    grounding = _grounding_block(query, tiers, deduped, iso_at)

    return {
        "status": "ok" if any_results else "no_results",
        "query": query,
        "retrieved_at": iso_at,
        "tiers": tiers,
        "evidence": deduped,
        "evidence_count": len(deduped),
        "grounding_block_markdown": grounding,
    }
