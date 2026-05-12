"""Tool implementations for grace-slack."""

from __future__ import annotations

from typing import Any

from grace_shared.errors import (
    NotFoundError,
    UpstreamError,
    ValidationError,
    to_error_dict,
)

from grace_slack import (
    DEFAULT_DAYS_BACK,
    DEFAULT_LIMIT,
    MAX_DAYS_BACK,
    MAX_LIMIT,
    SKIPPED_SUBTYPES,
)
from grace_slack.client import SlackClient, _ts_to_iso


def _validate_days_back(days_back: Any) -> int:
    try:
        n = int(days_back)
    except Exception as exc:
        raise ValidationError("days_back must be an integer") from exc
    if n < 1:
        raise ValidationError("days_back must be >= 1")
    if n > MAX_DAYS_BACK:
        raise ValidationError(f"days_back must be <= {MAX_DAYS_BACK}")
    return n


def _validate_limit(limit: Any, default: int = DEFAULT_LIMIT) -> int:
    try:
        n = int(limit)
    except Exception:
        n = default
    if n < 1:
        n = default
    return min(n, MAX_LIMIT)


def _keyword_match(text: str, query: str) -> bool:
    if not query.strip():
        return True
    needles = [t.lower() for t in query.split() if t.strip()]
    text_l = text.lower()
    return all(n in text_l for n in needles)


def _shape_message(client: SlackClient, msg: dict) -> dict:
    user_id = msg.get("user", "") or ""
    ts = msg.get("ts", "") or ""
    thread_ts = msg.get("thread_ts", "") or ""
    reply_count = msg.get("reply_count", 0) or 0
    text = msg.get("text", "") or ""
    permalink = client.resolve_permalink(ts) if ts else ""
    sender_name = client.resolve_sender_name(user_id) if user_id else ""
    return {
        "ts": ts,
        "iso_date": _ts_to_iso(ts),
        "user_id": user_id,
        "sender_name": sender_name,
        "is_authoritative": client.is_authoritative(user_id),
        "text": text,
        "thread_ts": thread_ts,
        "has_thread": bool(thread_ts) or reply_count > 0,
        "reply_count": int(reply_count) if isinstance(reply_count, (int, float)) else 0,
        "permalink": permalink,
    }


def search_pmo(
    client: SlackClient,
    query: Any,
    *,
    days_back: Any = DEFAULT_DAYS_BACK,
    limit: Any = DEFAULT_LIMIT,
    authoritative_only: Any = True,
) -> dict:
    if not isinstance(query, str):
        return to_error_dict(ValidationError("query must be a string"))
    try:
        d = _validate_days_back(days_back)
    except ValidationError as exc:
        return to_error_dict(exc)
    lim = _validate_limit(limit)
    auth_only = bool(authoritative_only)
    auth_ids = client.authoritative_user_ids

    if auth_only and not auth_ids:
        return {
            "status": "no_results",
            "channel": client.channel_id,
            "query": query,
            "days_back": d,
            "authoritative_only": True,
            "authoritative_senders_configured": 0,
            "warning": (
                "AUTHORITATIVE_SLACK_USER_IDS env var not set. Refusing to "
                "return Slack results without an authoritative-sender filter."
            ),
            "results": [],
        }

    try:
        raw = client.fetch_history(days_back=d)
    except NotFoundError as exc:
        return to_error_dict(exc)
    except UpstreamError as exc:
        return to_error_dict(exc)

    filtered: list[dict] = []
    for m in raw:
        subtype = m.get("subtype", "") or ""
        if subtype in SKIPPED_SUBTYPES:
            continue
        if "bot_id" in m and not m.get("user"):
            continue
        if auth_only and not client.is_authoritative(m.get("user", "") or ""):
            continue
        text = m.get("text", "") or ""
        if not _keyword_match(text, query):
            continue
        filtered.append(m)

    # Sort newest-first
    def _key(msg: dict) -> float:
        try:
            return float(msg.get("ts", "0"))
        except Exception:
            return 0.0

    filtered.sort(key=_key, reverse=True)
    shaped = [_shape_message(client, m) for m in filtered[:lim]]
    return {
        "status": "ok" if shaped else "no_results",
        "channel": client.channel_id,
        "query": query,
        "days_back": d,
        "authoritative_only": auth_only,
        "authoritative_senders_configured": len(auth_ids),
        "results": shaped,
    }


def get_thread(client: SlackClient, thread_ts: Any, *, limit: Any = 100) -> dict:
    if not isinstance(thread_ts, str) or not thread_ts.strip():
        return to_error_dict(ValidationError("thread_ts is required"))
    lim = _validate_limit(limit, default=100)
    try:
        msgs = client.fetch_thread(thread_ts=thread_ts.strip(), limit=lim)
    except NotFoundError as exc:
        return to_error_dict(exc)
    except UpstreamError as exc:
        return to_error_dict(exc)

    # Order: parent first, replies chronological by ts ascending
    def _key(msg: dict) -> float:
        try:
            return float(msg.get("ts", "0"))
        except Exception:
            return 0.0

    msgs.sort(key=_key)
    shaped = [_shape_message(client, m) for m in msgs]
    return {
        "status": "ok",
        "channel": client.channel_id,
        "thread_ts": thread_ts,
        "message_count": len(shaped),
        "messages": shaped,
    }
