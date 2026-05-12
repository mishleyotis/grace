"""Stress tests OR-S1..OR-S7 for the ranking layer."""

from __future__ import annotations

import pytest
from grace_orchestrator.bundle import retrieve_bundle
from or_helpers import (
    days_ago_ts,
    drive_map_result,
    make_retriever,
    make_slack_retriever,
    site_mirror_result,
    slack_result,
)


async def _bundle(sm, dm, sl, *, auth_only=True):
    return await retrieve_bundle(
        query="kickoff",
        site_mirror_search=make_retriever({"results": sm}),
        drive_map_search=make_retriever({"results": dm}),
        slack_search_pmo=make_slack_retriever({"results": sl}),
        slack_authoritative_only=auth_only,
    )


@pytest.mark.asyncio
async def test_OR_S1_site_mirror_outranks_drive_map():
    sm = [site_mirror_result(name="Kickoff", url="https://sites.google.com/x/k", snippet="...")]
    dm = [
        drive_map_result(
            name="Plain Kickoff Doc",
            url="https://drive.google.com/d/123",
            inner_score=0,
        )
    ]
    out = await _bundle(sm, dm, [])
    assert out["evidence"][0]["tier"] == "site_mirror"


@pytest.mark.asyncio
async def test_OR_S2_drive_map_outranks_slack():
    """Equal-strength: drive_map with a typical search match outranks an
    authoritative recent Slack message of equivalent topical match.

    drive_map = 80 (base) + 30 (inner kickoff match)            = 110
    slack     = 60 (base) + 20 (auth) + 10 (recency) + 3 (thread) = 93
    """
    dm = [
        drive_map_result(
            name="kickoff agenda",
            url="https://drive.google.com/d/123",
            inner_score=30,
        )
    ]
    sl = [
        slack_result(
            permalink="https://slack/p/1",
            is_authoritative=True,
            ts=days_ago_ts(1),
            reply_count=2,
        )
    ]
    out = await _bundle([], dm, sl)
    assert out["evidence"][0]["tier"] == "drive_map"


@pytest.mark.asyncio
async def test_OR_S3_ZS_boost_within_drive_map():
    dm = [
        drive_map_result(name="other", url="https://drive/a", inner_score=70),
        drive_map_result(name="ZS_Source", url="https://drive/b", inner_score=70),
    ]
    out = await _bundle([], dm, [])
    drive_items = [e for e in out["evidence"] if e["tier"] == "drive_map"]
    assert drive_items[0]["title"] == "ZS_Source"


@pytest.mark.asyncio
async def test_OR_S4_high_ZS_can_outrank_site_mirror():
    sm = [site_mirror_result(name="Plain", url="https://sites.google.com/x/p")]
    dm = [
        drive_map_result(
            name="ZS_Top",
            url="https://drive/zs",
            inner_score=90,  # capped at 80
        )
    ]
    out = await _bundle(sm, dm, [])
    # site_mirror: 100; drive_map: 80 + 30 (ZS_) + 80 (capped) = 190
    assert out["evidence"][0]["title"] == "ZS_Top"


@pytest.mark.asyncio
async def test_OR_S5_authoritative_slack_outranks_non_auth():
    auth = slack_result(
        permalink="https://slack/p/auth",
        user_id="U_KALLEN",
        is_authoritative=True,
        ts=days_ago_ts(1),
    )
    non = slack_result(
        permalink="https://slack/p/non",
        user_id="U_RANDOM",
        is_authoritative=False,
        ts=days_ago_ts(1),
    )
    out = await _bundle([], [], [auth, non], auth_only=False)
    slack_evidence = [e for e in out["evidence"] if e["tier"] == "slack"]
    assert slack_evidence[0]["title"] in ("Kallen", "U_KALLEN")


@pytest.mark.asyncio
async def test_OR_S6_non_auth_slack_drops_below_other_tiers():
    sl = [
        slack_result(
            permalink="https://slack/p/non",
            user_id="U_RANDOM",
            is_authoritative=False,
            ts=days_ago_ts(1),
        )
    ]
    sm = [site_mirror_result(name="Plain", url="https://sites.google.com/x/p")]
    out = await _bundle(sm, [], sl, auth_only=False)
    slack_scores = [e["score"] for e in out["evidence"] if e["tier"] == "slack"]
    sm_scores = [e["score"] for e in out["evidence"] if e["tier"] == "site_mirror"]
    assert max(slack_scores) < min(sm_scores)


@pytest.mark.asyncio
async def test_OR_S7_recency_bonus_on_slack():
    fresh = slack_result(
        permalink="https://slack/p/fresh",
        user_id="U_KALLEN",
        is_authoritative=True,
        ts=days_ago_ts(1),
    )
    old = slack_result(
        permalink="https://slack/p/old",
        user_id="U_KALLEN",
        is_authoritative=True,
        ts=days_ago_ts(2000),
    )
    out = await _bundle([], [], [fresh, old])
    urls = [e["url"] for e in out["evidence"] if e["tier"] == "slack"]
    assert urls[0].endswith("/fresh")
