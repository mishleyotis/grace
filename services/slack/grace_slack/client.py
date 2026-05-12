"""Slack client wrapper.

Implements:
  - conversations.history (paginated, time-bounded)
  - users.info (cached)
  - chat.getPermalink
  - conversations.replies (for slack_get_thread)

Strict rules:
  - Bot token must start with 'xoxb-' (otherwise RuntimeError at startup).
  - SKIPPED_SUBTYPES are filtered before scoring or ranking.
  - User lookups and permalink lookups degrade gracefully.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from grace_shared.errors import NotFoundError, UpstreamError

from grace_slack import (
    PMO_CHANNEL_ID,
)


def _ts_to_iso(ts: str) -> str:
    if not ts:
        return ""
    try:
        seconds = float(ts)
    except (TypeError, ValueError):
        return ""
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, OSError, ValueError):
        return ""


def validate_bot_token_or_raise(token: str) -> None:
    if not isinstance(token, str) or not token.startswith("xoxb-"):
        raise RuntimeError(
            "SLACK_BOT_TOKEN missing or invalid (expected an xoxb- prefixed bot token)"
        )


class SlackTransport:
    """Pluggable transport so tests can run without slack_sdk."""

    def conversations_history(
        self, *, channel: str, oldest: str, limit: int, cursor: str | None = None
    ) -> dict:
        raise NotImplementedError

    def conversations_replies(self, *, channel: str, ts: str, limit: int) -> dict:
        raise NotImplementedError

    def users_info(self, *, user_id: str) -> dict:
        raise NotImplementedError

    def chat_get_permalink(self, *, channel: str, message_ts: str) -> dict:
        raise NotImplementedError


class SlackClient:
    """High-level wrapper used by tools."""

    def __init__(
        self,
        transport: SlackTransport,
        *,
        channel_id: str = PMO_CHANNEL_ID,
        authoritative_user_ids: Iterable[str] | None = None,
    ) -> None:
        self._t = transport
        self._channel_id = channel_id
        self._auth_ids = set(authoritative_user_ids or [])
        self._user_cache: dict[str, str] = {}

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def authoritative_user_ids(self) -> set[str]:
        return set(self._auth_ids)

    def is_authoritative(self, user_id: str) -> bool:
        return bool(user_id) and user_id in self._auth_ids

    def resolve_sender_name(self, user_id: str) -> str:
        if not user_id:
            return ""
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            info = self._t.users_info(user_id=user_id)
            profile = info.get("user", {}).get("profile", {}) if isinstance(info, dict) else {}
            name = (
                profile.get("real_name")
                or profile.get("display_name")
                or info.get("user", {}).get("name", "")
            )
        except Exception:
            name = ""
        name = name or ""
        self._user_cache[user_id] = name
        return name

    def resolve_permalink(self, ts: str) -> str:
        try:
            resp = self._t.chat_get_permalink(channel=self._channel_id, message_ts=ts)
            return resp.get("permalink", "") if isinstance(resp, dict) else ""
        except Exception:
            return ""

    def fetch_history(self, *, days_back: int, max_pages: int = 10) -> list[dict]:
        oldest_dt = time.time() - days_back * 86_400
        oldest = f"{oldest_dt:.6f}"

        messages: list[dict] = []
        cursor: str | None = None
        pages = 0
        while pages < max_pages:
            pages += 1
            try:
                resp = self._t.conversations_history(
                    channel=self._channel_id, oldest=oldest, limit=200, cursor=cursor
                )
            except _SlackChannelNotFound as exc:
                raise NotFoundError(
                    f"channel {self._channel_id} not found or bot lacks access"
                ) from exc
            except _SlackRateLimited as exc:
                raise UpstreamError(f"slack ratelimited: {exc}") from exc
            except Exception as exc:
                raise UpstreamError(f"conversations.history failed: {exc}") from exc
            messages.extend(resp.get("messages", []) or [])
            md = resp.get("response_metadata", {}) or {}
            cursor = md.get("next_cursor", "") or None
            if not cursor:
                break
        return messages

    def fetch_thread(self, *, thread_ts: str, limit: int = 100) -> list[dict]:
        try:
            resp = self._t.conversations_replies(
                channel=self._channel_id, ts=thread_ts, limit=limit
            )
        except _SlackChannelNotFound as exc:
            raise NotFoundError("thread not found") from exc
        except _SlackRateLimited as exc:
            raise UpstreamError(f"slack ratelimited: {exc}") from exc
        except _SlackThreadNotFound as exc:
            raise NotFoundError("thread not found") from exc
        except Exception as exc:
            raise UpstreamError(f"conversations.replies failed: {exc}") from exc
        msgs = resp.get("messages", []) or []
        if not msgs:
            raise NotFoundError("thread not found")
        return msgs


# Sentinel exceptions used by tests and the real-Slack adapter
class _SlackChannelNotFound(Exception):
    pass


class _SlackThreadNotFound(Exception):
    pass


class _SlackRateLimited(Exception):
    pass


# ---------------------------------------------------------------------------
# Adapter for the real slack_sdk (only loaded at runtime)
# ---------------------------------------------------------------------------
class SlackSDKTransport(SlackTransport):  # pragma: no cover
    def __init__(self, token: str) -> None:
        validate_bot_token_or_raise(token)
        from slack_sdk import WebClient  # type: ignore

        self._client = WebClient(token=token)

    def _call(self, method: str, **kwargs: Any) -> dict:
        from slack_sdk.errors import SlackApiError  # type: ignore

        try:
            resp = getattr(self._client, method)(**kwargs)
            return resp.data
        except SlackApiError as exc:
            err = (exc.response.data or {}).get("error", "") if exc.response else ""
            if err == "channel_not_found":
                raise _SlackChannelNotFound(err) from exc
            if err == "thread_not_found":
                raise _SlackThreadNotFound(err) from exc
            if err == "ratelimited":
                raise _SlackRateLimited(err) from exc
            raise UpstreamError(f"slack api error: {err or exc}") from exc

    def conversations_history(self, *, channel, oldest, limit, cursor=None):
        return self._call(
            "conversations_history",
            channel=channel,
            oldest=oldest,
            limit=limit,
            cursor=cursor or "",
        )

    def conversations_replies(self, *, channel, ts, limit):
        return self._call(
            "conversations_replies", channel=channel, ts=ts, limit=limit
        )

    def users_info(self, *, user_id):
        return self._call("users_info", user=user_id)

    def chat_get_permalink(self, *, channel, message_ts):
        return self._call(
            "chat_getPermalink", channel=channel, message_ts=message_ts
        )


def build_default_client() -> SlackClient:  # pragma: no cover
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    validate_bot_token_or_raise(token)
    auth_ids_csv = os.environ.get("AUTHORITATIVE_SLACK_USER_IDS", "")
    auth_ids = [x.strip() for x in auth_ids_csv.split(",") if x.strip()]
    transport = SlackSDKTransport(token)
    return SlackClient(transport, authoritative_user_ids=auth_ids)
