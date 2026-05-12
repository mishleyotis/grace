"""Unit tests for the Apps Script client."""


import pytest
from grace_shared.errors import UpstreamError, ValidationError
from grace_site_mirror.client import MAX_SEARCH_LIMIT, AppsScriptClient
from sm_helpers import FakeHttpClient, FakeResponse, json_response  # noqa: E402


@pytest.mark.asyncio
async def test_rejects_unknown_action():
    c = AppsScriptClient("https://x", http_client=FakeHttpClient(json_response({})))
    with pytest.raises(ValidationError):
        await c.call("bogusAction", {})


@pytest.mark.asyncio
async def test_rejects_empty_endpoint():
    with pytest.raises(ValidationError):
        AppsScriptClient("")


@pytest.mark.asyncio
async def test_http_5xx_becomes_upstream_error():
    """SM-S3-style: bad HTTP -> upstream_error."""
    resp = FakeResponse(status_code=500, text="boom", _body={})
    c = AppsScriptClient("https://x", http_client=FakeHttpClient(resp))
    with pytest.raises(UpstreamError, match="HTTP 500"):
        await c.call("getURLIndex")


@pytest.mark.asyncio
async def test_non_json_becomes_upstream_error():
    resp = FakeResponse(
        status_code=200, headers={"content-type": "text/html"}, _body={}
    )
    c = AppsScriptClient("https://x", http_client=FakeHttpClient(resp))
    with pytest.raises(UpstreamError, match="non-JSON content-type"):
        await c.call("getURLIndex")


@pytest.mark.asyncio
async def test_malformed_json_becomes_upstream_error():
    """SM-S3."""
    resp = FakeResponse(_body=ValueError("expecting value"))
    c = AppsScriptClient("https://x", http_client=FakeHttpClient(resp))
    with pytest.raises(UpstreamError, match="malformed JSON"):
        await c.call("getURLIndex")


@pytest.mark.asyncio
async def test_request_error_becomes_upstream_error():
    """SM-S2: timeout / network exception is mapped, not leaked."""

    class Boom(Exception):
        pass

    c = AppsScriptClient("https://x", http_client=FakeHttpClient(Boom("timeout")))
    with pytest.raises(UpstreamError, match="request failed"):
        await c.call("getURLIndex")


def test_max_search_limit_constant():
    assert MAX_SEARCH_LIMIT == 50
