"""Orchestrator test fixtures."""

from __future__ import annotations

import time
from typing import Awaitable, Callable


def days_ago_ts(days: float) -> str:
    return f"{time.time() - days * 86_400:.6f}"


def site_mirror_result(*, name: str, url: str, snippet: str = "") -> dict:
    return {"name": name, "siteUrl": url, "snippet": snippet}


def drive_map_result(
    *,
    name: str,
    url: str,
    inner_score: int = 50,
    summary: str = "",
    modified: str = "",
) -> dict:
    return {
        "name": name,
        "url": url,
        "score": inner_score,
        "summary": summary,
        "modified": modified,
    }


def slack_result(
    *,
    permalink: str,
    user_id: str = "U_KALLEN",
    sender_name: str = "Kallen",
    is_authoritative: bool = True,
    text: str = "kickoff is important",
    ts: str | None = None,
    reply_count: int = 0,
) -> dict:
    return {
        "permalink": permalink,
        "user_id": user_id,
        "sender_name": sender_name,
        "is_authoritative": is_authoritative,
        "text": text,
        "ts": ts or days_ago_ts(2),
        "iso_date": "",
        "reply_count": reply_count,
        "has_thread": reply_count > 0,
    }


def make_retriever(payload: dict | Exception) -> Callable[[str, int], Awaitable[dict]]:
    async def _r(query: str, limit: int) -> dict:  # noqa: ARG001
        if isinstance(payload, Exception):
            raise payload
        return payload

    return _r


def make_slack_retriever(payload):
    async def _r(query: str, limit: int, auth_only: bool) -> dict:  # noqa: ARG001
        if isinstance(payload, Exception):
            raise payload
        return payload

    return _r
