"""Bundle-shape and resilience tests (OR-S14..OR-S20)."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from grace_orchestrator import MAX_PER_TIER_LIMIT
from grace_orchestrator.bundle import retrieve_bundle
from or_helpers import (
    drive_map_result,
    make_retriever,
    make_slack_retriever,
    site_mirror_result,
)


@pytest.mark.asyncio
async def test_OR_S14_tier_failure_isolation():
    sm = make_retriever(RuntimeError("boom"))
    dm = make_retriever({"results": [drive_map_result(name="d", url="https://d/1")]})
    sl = make_slack_retriever({"results": []})
    out = await retrieve_bundle(
        query="x",
        site_mirror_search=sm,
        drive_map_search=dm,
        slack_search_pmo=sl,
    )
    assert out["tiers"]["site_mirror"]["status"].startswith("error:")
    assert out["tiers"]["drive_map"]["status"] == "ok"
    assert out["tiers"]["slack"]["status"] == "no_results"
    assert any(e["tier"] == "drive_map" for e in out["evidence"])


@pytest.mark.asyncio
async def test_OR_S15_all_tiers_fail():
    boom = RuntimeError("boom")
    out = await retrieve_bundle(
        query="x",
        site_mirror_search=make_retriever(boom),
        drive_map_search=make_retriever(boom),
        slack_search_pmo=make_slack_retriever(boom),
    )
    assert out["status"] == "no_results"
    assert out["evidence"] == []
    assert all(
        out["tiers"][t]["status"].startswith("error:")
        for t in ("site_mirror", "drive_map", "slack")
    )


@pytest.mark.asyncio
async def test_OR_S16_authoritative_flag_passes_through():
    captured = {}

    async def slack_capture(query, limit, auth_only):
        captured["auth_only"] = auth_only
        return {"results": []}

    await retrieve_bundle(
        query="x",
        site_mirror_search=make_retriever({"results": []}),
        drive_map_search=make_retriever({"results": []}),
        slack_search_pmo=slack_capture,
        slack_authoritative_only=False,
    )
    assert captured["auth_only"] is False


@pytest.mark.asyncio
async def test_OR_S17_concurrent_bundles_no_blocking():
    async def slow_sm(query, limit):
        await asyncio.sleep(0.05)
        return {"results": []}

    async def slow_dm(query, limit):
        await asyncio.sleep(0.05)
        return {"results": []}

    async def slow_sl(query, limit, auth_only):
        await asyncio.sleep(0.05)
        return {"results": []}

    start = asyncio.get_event_loop().time()
    await asyncio.gather(
        *(
            retrieve_bundle(
                query="x",
                site_mirror_search=slow_sm,
                drive_map_search=slow_dm,
                slack_search_pmo=slow_sl,
            )
            for _ in range(10)
        )
    )
    elapsed = asyncio.get_event_loop().time() - start
    # Within each bundle, the 3 tiers fan out in parallel (one ~0.05s slot).
    # 10 parallel bundles should still complete well under 10x serial latency.
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_OR_S18_grounding_block_shape():
    out = await retrieve_bundle(
        query="kickoff",
        site_mirror_search=make_retriever(
            {"results": [site_mirror_result(name="X", url="https://sites.google.com/x")]}
        ),
        drive_map_search=make_retriever({"results": []}),
        slack_search_pmo=make_slack_retriever({"results": []}),
    )
    md = out["grounding_block_markdown"]
    assert "Tier 1" in md
    assert "Tier 2" in md
    assert "Tier 3" in md
    assert "Top evidence" in md


@pytest.mark.asyncio
async def test_OR_S19_per_tier_limit_clamped():
    captured = {}

    async def sm(query, limit):
        captured["limit"] = limit
        return {"results": []}

    await retrieve_bundle(
        query="x",
        site_mirror_search=sm,
        drive_map_search=make_retriever({"results": []}),
        slack_search_pmo=make_slack_retriever({"results": []}),
        per_tier_limit=999,
    )
    assert captured["limit"] == MAX_PER_TIER_LIMIT


@pytest.mark.asyncio
async def test_OR_S20_retrieved_at_is_iso_utc():
    out = await retrieve_bundle(
        query="x",
        site_mirror_search=make_retriever({"results": []}),
        drive_map_search=make_retriever({"results": []}),
        slack_search_pmo=make_slack_retriever({"results": []}),
    )
    # Z-suffix → strip and parse
    iso = out["retrieved_at"].replace("Z", "+00:00")
    parsed = datetime.fromisoformat(iso)
    assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_query_validation():
    out = await retrieve_bundle(
        query="",
        site_mirror_search=make_retriever({"results": []}),
        drive_map_search=make_retriever({"results": []}),
        slack_search_pmo=make_slack_retriever({"results": []}),
    )
    assert out["error"] == "validation_error"


@pytest.mark.asyncio
async def test_evidence_ranks_assigned():
    out = await retrieve_bundle(
        query="x",
        site_mirror_search=make_retriever(
            {
                "results": [
                    site_mirror_result(name="A", url="https://sites.google.com/x/a"),
                    site_mirror_result(name="B", url="https://sites.google.com/x/b"),
                ]
            }
        ),
        drive_map_search=make_retriever({"results": []}),
        slack_search_pmo=make_slack_retriever({"results": []}),
    )
    ranks = [e["rank"] for e in out["evidence"]]
    assert ranks == list(range(1, len(ranks) + 1))
