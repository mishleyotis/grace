"""Cross-tier URL deduplication.

canonical_url_key(url) = lowercase(scheme + host) + path.rstrip('/')
                        with query and fragment stripped.

Items that share a canonical key merge into one evidence item with:
    tiers_present = sorted({tier names in group})
    score_sources = {tier: max_score_seen_in_tier}
    score         = max(scores) + (N - 1) * 2     ← concurrence bonus
Missing snippet/iso_date/sender_name fields are filled from secondaries.
Empty URLs are NOT merged (passthrough).
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse


def canonical_url_key(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def dedup(items: Iterable[dict]) -> list[dict]:
    """Merge items that share a canonical URL; passthrough empty-URL items."""
    items = list(items)
    groups: dict[str, list[dict]] = {}
    passthrough: list[dict] = []
    for it in items:
        key = canonical_url_key(it.get("url"))
        if not key:
            passthrough.append(it)
            continue
        groups.setdefault(key, []).append(it)

    merged: list[dict] = []
    for _key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        # Sort by individual score desc; primary = highest
        group.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
        primary = dict(group[0])
        # Fill missing fields from secondaries
        for sec in group[1:]:
            for field in ("snippet", "iso_date", "sender_name", "title"):
                if not primary.get(field) and sec.get(field):
                    primary[field] = sec[field]
        primary["tiers_present"] = sorted({g["tier"] for g in group})
        primary["score_sources"] = {
            t: max((g["score"] for g in group if g["tier"] == t), default=0)
            for t in primary["tiers_present"]
        }
        # Concurrence bonus
        primary["score"] = int(primary["score"]) + (len(primary["tiers_present"]) - 1) * 2
        merged.append(primary)
    merged.extend(passthrough)
    return merged
