"""Integration-style tests for the tool layer: extra coverage."""

from __future__ import annotations

from grace_slack import tools
from sl_helpers import FakeTransport, mk_msg, ts_days_ago


def test_search_pmo_no_results_when_history_empty(transport: FakeTransport, client):
    out = tools.search_pmo(client, "kickoff")
    assert out["status"] == "no_results"


def test_search_pmo_query_keywords_all_required(transport: FakeTransport, client):
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="kickoff agenda"),
        mk_msg(ts=ts_days_ago(2), user="U_KALLEN", text="kickoff alone"),
    ]
    out = tools.search_pmo(client, "kickoff agenda")
    assert [r["text"] for r in out["results"]] == ["kickoff agenda"]


def test_search_pmo_includes_authoritative_count(transport: FakeTransport, client):
    transport.messages = [
        mk_msg(ts=ts_days_ago(1), user="U_KALLEN", text="kickoff"),
    ]
    out = tools.search_pmo(client, "kickoff")
    assert out["authoritative_senders_configured"] == 6


def test_get_thread_validation(client):
    out = tools.get_thread(client, "")
    assert out["error"] == "validation_error"
