"""Evidence scoring.

Cross-tier authority (per design §4.4):
    site_mirror : 100  (canonical Source of Truth)
    drive_map   :  80  (supporting documents)
    slack       :  60  (recent context, never overrides 1-2)

drive_map bonuses:
    +30 if name starts with ZS_
    + inner search score capped at +80

slack bonuses / penalties:
    +20 if message is from authoritative sender
    -50 if NOT authoritative (only relevant when authoritative_only=False)
    +0-10 recency
    +3 if message has thread replies
"""

from __future__ import annotations

import time

from grace_orchestrator import TIER_WEIGHT


def _now_seconds() -> float:
    return time.time()


def _slack_recency_bonus(ts: str) -> int:
    try:
        t = float(ts)
    except Exception:
        return 0
    age_days = (_now_seconds() - t) / 86_400.0
    if age_days < 0:
        age_days = 0
    if age_days <= 30:
        return 10
    if age_days <= 90:
        return 5
    if age_days <= 365:
        return 2
    return 0


def score_site_mirror(item: dict) -> int:
    return TIER_WEIGHT["site_mirror"]


def score_drive_map(item: dict) -> int:
    score = TIER_WEIGHT["drive_map"]
    name = (item.get("name") or "").strip()
    if name.startswith("ZS_"):
        score += 30
    inner = int(item.get("score") or 0)
    score += min(inner, 80)
    return score


def score_slack(item: dict, *, default_authoritative_only: bool) -> int:
    score = TIER_WEIGHT["slack"]
    if item.get("is_authoritative"):
        score += 20
    elif not default_authoritative_only:
        score -= 50
    score += _slack_recency_bonus(item.get("ts") or "")
    if item.get("has_thread") or int(item.get("reply_count") or 0) > 0:
        score += 3
    return score


def normalize_site_mirror_items(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for it in items or []:
        url = it.get("siteUrl") or it.get("url") or ""
        if not url:
            continue
        out.append(
            {
                "tier": "site_mirror",
                "title": it.get("name") or it.get("title") or url,
                "url": url,
                "snippet": it.get("snippet") or "",
                "iso_date": "",
                "score": score_site_mirror(it),
                "_raw": it,
            }
        )
    return out


def normalize_drive_map_items(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for it in items or []:
        url = it.get("url") or ""
        out.append(
            {
                "tier": "drive_map",
                "title": it.get("name") or "(unknown)",
                "url": url,
                "snippet": (it.get("summary") or "")[:300],
                "iso_date": it.get("modified") or "",
                "score": score_drive_map(it),
                "_raw": it,
            }
        )
    return out


def normalize_slack_items(items: list[dict], *, default_authoritative_only: bool) -> list[dict]:
    out: list[dict] = []
    for it in items or []:
        url = it.get("permalink") or ""
        out.append(
            {
                "tier": "slack",
                "title": it.get("sender_name") or it.get("user_id") or "Slack",
                "url": url,
                "snippet": (it.get("text") or "")[:400],
                "iso_date": it.get("iso_date") or "",
                "sender_name": it.get("sender_name", ""),
                "is_authoritative": bool(it.get("is_authoritative")),
                "score": score_slack(
                    it, default_authoritative_only=default_authoritative_only
                ),
                "_raw": it,
            }
        )
    return out
