"""Stress tests for the site-mirror tool layer (SM-S1, S2, S3, S5, S6, S7, plus dedup)."""

from __future__ import annotations

import asyncio
import json

import pytest
from grace_shared.url_canon import MIRROR_DOC_ID
from grace_site_mirror import tools
from grace_site_mirror.client import AppsScriptClient
from sm_helpers import FakeHttpClient, FakeResponse, json_response  # noqa: E402


def _client(handler) -> AppsScriptClient:
    return AppsScriptClient("https://x", http_client=FakeHttpClient(handler))


# ---------- SM-S1: URL scrubbing under concurrent calls ----------
@pytest.mark.asyncio
async def test_SM_S1_scrub_under_concurrency():
    """50 concurrent searches; mirror doc ID and Apps Script URL never leak."""
    crafted_body = {
        "results": [
            {
                "name": "Kickoff Phase",
                "siteUrl": "https://sites.google.com/zennify.com/delivery/kickoff",
                "url": f"https://docs.google.com/document/d/{MIRROR_DOC_ID}/edit",
                "snippet": "kickoff snippet",
            },
            {
                "name": "Other",
                "siteUrl": "https://sites.google.com/zennify.com/delivery/other",
                "url": "https://script.google.com/macros/s/SECRET/exec?action=getSection",
                "snippet": "x",
            },
        ]
    }
    c = _client(lambda _u, _p: json_response(crafted_body))
    results = await asyncio.gather(
        *(tools.site_mirror_search(c, "kickoff", 10) for _ in range(50))
    )
    serialized = json.dumps(results)
    assert MIRROR_DOC_ID not in serialized
    assert "script.google.com/macros/s/" not in serialized
    # And siteUrls survive
    for r in results:
        assert r["status"] == "ok"
        for item in r["results"]:
            assert item["siteUrl"].startswith(
                "https://sites.google.com/zennify.com/delivery/"
            )


# ---------- SM-S2: timeout resilience ----------
@pytest.mark.asyncio
async def test_SM_S2_timeout_resilience():
    class TimeoutErr(Exception):
        pass

    c = _client(TimeoutErr("connect timeout after 30s"))
    out = await tools.site_mirror_search(c, "kickoff", 10)
    assert out["error"] == "upstream_error"
    assert "request failed" in out["message"]


# ---------- SM-S3: malformed JSON ----------
@pytest.mark.asyncio
async def test_SM_S3_malformed_json():
    resp = FakeResponse(_body=ValueError("trailing garbage"))
    c = _client(resp)
    out = await tools.site_mirror_search(c, "kickoff", 10)
    assert out["error"] == "upstream_error"
    assert "malformed JSON" in out["message"]


# ---------- SM-S5: internal page-link drop ----------
@pytest.mark.asyncio
async def test_SM_S5_page_links_drop_internal():
    body = {
        "links": [
            {"text": "External", "url": "https://example.com/x", "type": "external"},
            {
                "text": "Mirror doc",
                "url": f"https://docs.google.com/document/d/{MIRROR_DOC_ID}/edit",
                "type": "internal",
            },
            {
                "text": "Apps Script",
                "url": "https://script.google.com/macros/s/x/exec",
                "type": "internal",
            },
            {
                "text": "Canonical",
                "url": "https://sites.google.com/zennify.com/delivery/kickoff",
                "type": "internal",
            },
        ]
    }
    c = _client(lambda _u, _p: json_response(body))
    out = await tools.site_mirror_get_page_links(c, "Kickoff")
    urls = {link["url"] for link in out["links"]}
    assert urls == {
        "https://example.com/x",
        "https://sites.google.com/zennify.com/delivery/kickoff",
    }


# ---------- SM-S6: limit clamping ----------
@pytest.mark.asyncio
async def test_SM_S6_limit_clamped_silently():
    body = {
        "results": [
            {
                "name": f"p{i}",
                "siteUrl": f"https://sites.google.com/zennify.com/delivery/p{i}",
            }
            for i in range(60)
        ]
    }
    c = _client(lambda _u, _p: json_response(body))
    out = await tools.site_mirror_search(c, "x", limit=999)
    assert out["status"] == "ok"
    assert len(out["results"]) <= 50


# ---------- SM-S7: empty query rejected before API call ----------
@pytest.mark.asyncio
async def test_SM_S7_empty_query_rejected():
    fake = FakeHttpClient(json_response({"results": []}))
    c = AppsScriptClient("https://x", http_client=fake)
    out = await tools.site_mirror_search(c, "", 10)
    assert out["error"] == "validation_error"
    assert fake.calls == []  # no downstream call


@pytest.mark.asyncio
async def test_empty_results_is_no_results_not_error():
    c = _client(lambda _u, _p: json_response({"results": []}))
    out = await tools.site_mirror_search(c, "anything", 10)
    assert out["status"] == "no_results"


@pytest.mark.asyncio
async def test_get_section_scrubs_site_url():
    body = {
        "name": "Kickoff",
        "siteUrl": "https://sites.google.com/zennify.com/delivery/kickoff",
        "content": "...",
        "paragraphs": ["a", "b"],
    }
    c = _client(lambda _u, _p: json_response(body))
    out = await tools.site_mirror_get_section(c, "Kickoff")
    assert out["status"] == "ok"
    assert out["siteUrl"].startswith("https://sites.google.com/")
    assert MIRROR_DOC_ID not in json.dumps(out)


@pytest.mark.asyncio
async def test_get_section_no_results_passthrough():
    c = _client(lambda _u, _p: json_response({"status": "no_results"}))
    out = await tools.site_mirror_get_section(c, "Bogus")
    assert out["status"] == "no_results"


@pytest.mark.asyncio
async def test_get_nav_map_scrubs_urls():
    body = {
        "nav": {
            "name": "root",
            "siteUrl": "https://sites.google.com/zennify.com/delivery/",
            "children": [
                {
                    "name": "doc",
                    "siteUrl": f"https://docs.google.com/document/d/{MIRROR_DOC_ID}/edit",
                }
            ],
        }
    }
    c = _client(lambda _u, _p: json_response(body))
    out = await tools.site_mirror_get_nav_map(c)
    assert MIRROR_DOC_ID not in json.dumps(out)


@pytest.mark.asyncio
async def test_get_url_index_scrubs():
    body = {
        "pages": [
            {
                "name": "p",
                "siteUrl": "https://sites.google.com/zennify.com/delivery/p",
                "sitePath": "/p",
            },
        ]
    }
    c = _client(lambda _u, _p: json_response(body))
    out = await tools.site_mirror_get_url_index(c)
    assert out["status"] == "ok"
    assert out["pages"][0]["siteUrl"].startswith(
        "https://sites.google.com/zennify.com/"
    )


@pytest.mark.asyncio
async def test_validation_error_on_blank_page_name():
    c = _client(lambda _u, _p: json_response({"links": []}))
    out = await tools.site_mirror_get_page_links(c, "  ")
    assert out["error"] == "validation_error"


@pytest.mark.asyncio
async def test_concurrent_mixed_tools_no_state_bleed():
    """SM-S10: 20 concurrent calls to different tools — all correct."""
    body_search = {"results": [{"name": "p", "siteUrl": "https://sites.google.com/zennify.com/delivery/p", "snippet": "..."}]}
    body_index = {"pages": [{"name": "p", "siteUrl": "https://sites.google.com/zennify.com/delivery/p"}]}

    def handler(_url, params):
        action = params.get("action")
        if action == "searchSections":
            return json_response(body_search)
        if action == "getURLIndex":
            return json_response(body_index)
        return json_response({})

    c = _client(handler)
    tasks = []
    for _ in range(10):
        tasks.append(tools.site_mirror_search(c, "x", 5))
        tasks.append(tools.site_mirror_get_url_index(c))
    out = await asyncio.gather(*tasks)
    assert all(r.get("status") == "ok" for r in out)
