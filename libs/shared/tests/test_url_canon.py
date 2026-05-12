"""Tests for url_canon — the security-critical scrubber."""

from grace_shared.url_canon import (
    APPS_SCRIPT_HOST_PATH,
    MIRROR_DOC_ID,
    canonicalize_zennify_url,
    looks_like_internal_url,
)


def test_mirror_doc_id_detected():
    assert looks_like_internal_url(
        f"https://docs.google.com/document/d/{MIRROR_DOC_ID}/edit"
    )


def test_apps_script_url_detected():
    assert looks_like_internal_url("https://script.google.com/macros/s/abc123/exec")


def test_external_url_not_internal():
    assert not looks_like_internal_url(
        "https://sites.google.com/zennify.com/delivery/kickoff"
    )


def test_empty_url_handled():
    assert not looks_like_internal_url(None)
    assert not looks_like_internal_url("")


def test_canonicalize_internal_falls_back_to_site_url():
    site = "https://sites.google.com/zennify.com/delivery/kickoff"
    assert (
        canonicalize_zennify_url("https://script.google.com/macros/s/x/exec", site)
        == site
    )


def test_canonicalize_external_passes_through():
    site = "https://sites.google.com/zennify.com/delivery/k"
    assert canonicalize_zennify_url(site, "") == site


def test_canonicalize_returns_empty_when_both_internal():
    assert (
        canonicalize_zennify_url(
            f"https://docs.google.com/document/d/{MIRROR_DOC_ID}/edit",
            "https://script.google.com/macros/s/x/exec",
        )
        == ""
    )


def test_constants():
    assert MIRROR_DOC_ID == "1KIudQjWefyoQfbdKMCVahIn3DOn-YNeo0KoZfdrB990"
    assert APPS_SCRIPT_HOST_PATH == "script.google.com/macros/s/"
