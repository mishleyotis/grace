"""Fixtures for slack tests."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pytest
from grace_slack.client import (
    SlackClient,
    SlackTransport,
    _SlackThreadNotFound,
)

AUTH_IDS = ["U_KALLEN", "U_MIKE", "U_BRYAN", "U_STEPH", "U_ROULEAU", "U_TOM"]
USER_NAMES = {
    "U_KALLEN": "Kallen",
    "U_MIKE": "Mike Theiler",
    "U_BRYAN": "Bryan Babb",
    "U_STEPH": "Stephanie Brooks",
    "U_ROULEAU": "Michael Rouleau",
    "U_TOM": "Tom Hedgecoth",
    "U_RANDOM": "Random Bob",
}


def mk_msg(
    *,
    ts: str,
    user: str,
    text: str,
    subtype: str = "",
    thread_ts: str = "",
    reply_count: int = 0,
    bot_id: str = "",
) -> dict:
    msg: dict[str, Any] = {"ts": ts, "user": user, "text": text}
    if subtype:
        msg["subtype"] = subtype
    if thread_ts:
        msg["thread_ts"] = thread_ts
    if reply_count:
        msg["reply_count"] = reply_count
    if bot_id:
        msg["bot_id"] = bot_id
    return msg


def ts_days_ago(days: float) -> str:
    return f"{time.time() - days * 86_400:.6f}"


@dataclass
class FakeTransport(SlackTransport):
    messages: list[dict] = field(default_factory=list)
    threads: dict[str, list[dict]] = field(default_factory=dict)
    fail_history_with: Exception | None = None
    fail_users_info_for: set[str] = field(default_factory=set)
    fail_permalink: bool = False
    users_info_calls: int = 0
    permalink_calls: int = 0

    def conversations_history(self, *, channel, oldest, limit, cursor=None):
        if self.fail_history_with is not None:
            raise self.fail_history_with
        try:
            o = float(oldest)
        except Exception:
            o = 0.0
        msgs = []
        for m in self.messages:
            try:
                t = float(m.get("ts") or 0)
            except (TypeError, ValueError):
                t = 0.0
            if t >= o:
                msgs.append(m)
        return {"messages": msgs}

    def conversations_replies(self, *, channel, ts, limit):
        if ts not in self.threads:
            raise _SlackThreadNotFound("thread_not_found")
        return {"messages": list(self.threads[ts])}

    def users_info(self, *, user_id):
        self.users_info_calls += 1
        if user_id in self.fail_users_info_for:
            raise Exception("users.info 500")
        name = USER_NAMES.get(user_id, "")
        return {"user": {"profile": {"real_name": name}, "name": name}}

    def chat_get_permalink(self, *, channel, message_ts):
        self.permalink_calls += 1
        if self.fail_permalink:
            raise Exception("permalink 500")
        return {"permalink": f"https://slack.example/{channel}/p{message_ts}"}


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def client(transport: FakeTransport) -> SlackClient:
    return SlackClient(
        transport, channel_id="C020PBE8J15", authoritative_user_ids=AUTH_IDS
    )


@pytest.fixture
def client_no_auth_ids(transport: FakeTransport) -> SlackClient:
    return SlackClient(transport, channel_id="C020PBE8J15", authoritative_user_ids=[])
