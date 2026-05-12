"""Slack client + tool unit tests covering SL-S1..SL-S17."""

from __future__ import annotations

import pytest
from grace_slack import tools
from grace_slack.client import (
    SlackClient,
    _SlackChannelNotFound,
    _SlackRateLimited,
    _ts_to_iso,
    validate_bot_token_or_raise,
)
from sl_helpers import (
    AUTH_IDS,
    FakeTransport,
    mk_msg,
    ts_days_ago,
)


def test_SL_S17_token_format_check():
    """Service startup raises if bot token has the wrong shape."""
    with pytest.raises(RuntimeError, match="xoxb-"):
        validate_bot_token_or_raise("not-a-bot-token")
    validate_bot_token_or_raise("xoxb-abc")


def test_SL_S1_auth_only_default_filters(transport: FakeTransport, client: SlackClient):
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="kickoff at Zennify"),
        mk_msg(ts=ts_days_ago(2), user="U_RANDOM", text="kickoff thoughts"),
    ]
    out = tools.search_pmo(client, "kickoff")
    assert out["status"] == "ok"
    assert out["authoritative_only"] is True
    assert all(r["is_authoritative"] for r in out["results"])
    assert all(r["user_id"] in AUTH_IDS for r in out["results"])


def test_SL_S2_misconfig_safety_net(transport: FakeTransport, client_no_auth_ids):
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="anything"),
    ]
    out = tools.search_pmo(client_no_auth_ids, "anything")
    assert out["status"] == "no_results"
    assert out["authoritative_senders_configured"] == 0
    assert "AUTHORITATIVE_SLACK_USER_IDS" in out["warning"]
    assert out["results"] == []


def test_SL_S3_authoritative_only_false_returns_all(
    transport: FakeTransport, client: SlackClient
):
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="kickoff x"),
        mk_msg(ts=ts_days_ago(2), user="U_RANDOM", text="kickoff y"),
    ]
    out = tools.search_pmo(client, "kickoff", authoritative_only=False)
    statuses = {r["is_authoritative"] for r in out["results"]}
    assert {True, False} == statuses


def test_SL_S4_system_messages_dropped(transport: FakeTransport, client: SlackClient):
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="join", subtype="channel_join"),
        mk_msg(ts=ts_days_ago(1), user="", text="hi", bot_id="B1"),
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="real kickoff message"),
    ]
    out = tools.search_pmo(client, "kickoff", authoritative_only=False)
    texts = [r["text"] for r in out["results"]]
    assert texts == ["real kickoff message"]


def test_SL_S5_recency_sort(transport: FakeTransport, client: SlackClient):
    transport.messages = [
        mk_msg(ts=ts_days_ago(30), user="U_MIKE", text="kickoff old"),
        mk_msg(ts=ts_days_ago(1), user="U_MIKE", text="kickoff fresh"),
        mk_msg(ts=ts_days_ago(10), user="U_MIKE", text="kickoff mid"),
    ]
    out = tools.search_pmo(client, "kickoff")
    texts = [r["text"] for r in out["results"]]
    assert texts == ["kickoff fresh", "kickoff mid", "kickoff old"]


def test_SL_S6_limit_respected(transport: FakeTransport, client: SlackClient):
    transport.messages = [
        mk_msg(ts=ts_days_ago(i + 1), user="U_KALLEN", text=f"kickoff {i}")
        for i in range(50)
    ]
    out = tools.search_pmo(client, "kickoff", limit=5)
    assert len(out["results"]) == 5


def test_SL_S7_days_back_upper_validation(client: SlackClient):
    out = tools.search_pmo(client, "x", days_back=731)
    assert out["error"] == "validation_error"


def test_SL_S8_days_back_zero(client: SlackClient):
    out = tools.search_pmo(client, "x", days_back=0)
    assert out["error"] == "validation_error"


def test_SL_S9_channel_not_found(transport: FakeTransport, client: SlackClient):
    transport.fail_history_with = _SlackChannelNotFound("channel_not_found")
    out = tools.search_pmo(client, "kickoff")
    assert out["error"] == "not_found"


def test_SL_S10_ratelimit_mapping(transport: FakeTransport, client: SlackClient):
    transport.fail_history_with = _SlackRateLimited("ratelimited")
    out = tools.search_pmo(client, "kickoff")
    assert out["error"] == "upstream_error"
    assert "ratelimited" in out["message"]


def test_SL_S11_user_lookup_graceful(
    transport: FakeTransport, client: SlackClient
):
    transport.fail_users_info_for = {"U_KALLEN"}
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="kickoff"),
    ]
    out = tools.search_pmo(client, "kickoff")
    assert out["results"][0]["sender_name"] == ""
    assert out["results"][0]["is_authoritative"] is True


def test_SL_S12_permalink_graceful(transport: FakeTransport, client: SlackClient):
    transport.fail_permalink = True
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="kickoff"),
    ]
    out = tools.search_pmo(client, "kickoff")
    assert out["results"][0]["permalink"] == ""
    assert out["results"][0]["text"] == "kickoff"


def test_SL_S13_thread_fetch_orders_parent_first(
    transport: FakeTransport, client: SlackClient
):
    parent_ts = ts_days_ago(2)
    reply1_ts = ts_days_ago(1.5)
    reply2_ts = ts_days_ago(1.0)
    transport.threads[parent_ts] = [
        mk_msg(ts=reply2_ts, user="U_BRYAN", text="reply 2"),
        mk_msg(ts=parent_ts, user="U_KALLEN", text="parent"),
        mk_msg(ts=reply1_ts, user="U_BRYAN", text="reply 1"),
    ]
    out = tools.get_thread(client, parent_ts)
    assert out["status"] == "ok"
    assert [m["text"] for m in out["messages"]] == ["parent", "reply 1", "reply 2"]


def test_SL_S14_thread_not_found(client: SlackClient):
    out = tools.get_thread(client, "1234567.000")
    assert out["error"] == "not_found"


def test_SL_S15_malformed_ts_tolerated(transport: FakeTransport, client: SlackClient):
    transport.messages = [
        mk_msg(ts="not-a-number", user="U_KALLEN", text="kickoff"),
    ]
    out = tools.search_pmo(client, "kickoff")
    # Filter pass-through: bad ts becomes 0 — message still included if oldest=0
    # Specifically we just check no crash:
    assert "results" in out
    if out["results"]:
        assert out["results"][0]["iso_date"] == ""


def test_SL_S16_user_cache_populates(transport: FakeTransport, client: SlackClient):
    transport.messages = [
        mk_msg(ts=ts_days_ago(i + 1), user="U_KALLEN", text=f"kickoff {i}")
        for i in range(20)
    ]
    tools.search_pmo(client, "kickoff", limit=20)
    # Only one users.info call thanks to the per-user cache
    assert transport.users_info_calls == 1


def test_ts_to_iso_basic():
    iso = _ts_to_iso(f"{1700000000}")
    assert iso.startswith("2023-")
