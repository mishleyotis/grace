"""Stress tests OR-S8..OR-S13 for cross-tier dedup."""

from __future__ import annotations

from grace_orchestrator.dedup import canonical_url_key, dedup


def _item(tier: str, url: str, score: int, **extra) -> dict:
    return {"tier": tier, "url": url, "title": tier, "score": score, **extra}


def test_OR_S8_two_tier_merge():
    out = dedup(
        [
            _item("site_mirror", "https://x.com/p", 100),
            _item("drive_map", "https://x.com/p", 110),
        ]
    )
    assert len(out) == 1
    item = out[0]
    assert item["tiers_present"] == ["drive_map", "site_mirror"]
    # primary chosen by max score (110); +2 concurrence bonus
    assert item["score"] == 112


def test_OR_S9_three_tier_merge():
    out = dedup(
        [
            _item("site_mirror", "https://x.com/p", 100),
            _item("drive_map", "https://x.com/p", 110),
            _item("slack", "https://x.com/p", 80),
        ]
    )
    assert len(out) == 1
    item = out[0]
    assert item["tiers_present"] == ["drive_map", "site_mirror", "slack"]
    assert item["score"] == 110 + 4


def test_OR_S10_trailing_slash():
    assert canonical_url_key("https://x.com/p") == canonical_url_key("https://x.com/p/")


def test_OR_S11_query_string_stripped():
    assert canonical_url_key("https://x.com/p?usp=sharing") == canonical_url_key(
        "https://x.com/p"
    )


def test_OR_S12_host_case_insensitive():
    assert canonical_url_key("https://Drive.Google.COM/p") == canonical_url_key(
        "https://drive.google.com/p"
    )


def test_OR_S13_empty_url_passthrough():
    out = dedup(
        [
            _item("site_mirror", "", 100, snippet="a"),
            _item("drive_map", "", 90, snippet="b"),
        ]
    )
    assert len(out) == 2


def test_fragment_stripped():
    assert canonical_url_key("https://x.com/p#section") == canonical_url_key(
        "https://x.com/p"
    )


def test_dedup_fills_missing_fields_from_secondary():
    out = dedup(
        [
            _item("drive_map", "https://x/p", 110, snippet=""),
            _item("site_mirror", "https://x/p", 100, snippet="from-tier-1"),
        ]
    )
    assert out[0]["snippet"] == "from-tier-1"
