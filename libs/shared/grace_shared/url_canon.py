"""URL canonicalization — scrubs internal URLs (mirror doc ID, Apps Script endpoint)
before they leave grace-site-mirror.

Critical invariant: tool outputs never contain the mirror doc ID
'1KIudQjWefyoQfbdKMCVahIn3DOn-YNeo0KoZfdrB990' or the
'https://script.google.com/macros/s/' Apps Script prefix.
"""

from __future__ import annotations

import re

MIRROR_DOC_ID = "1KIudQjWefyoQfbdKMCVahIn3DOn-YNeo0KoZfdrB990"
APPS_SCRIPT_HOST_PATH = "script.google.com/macros/s/"

_INTERNAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(re.escape(MIRROR_DOC_ID)),
    re.compile(r"script\.google\.com/macros/s/"),
)


def looks_like_internal_url(url: str | None) -> bool:
    """Return True if the URL references the mirror doc or Apps Script endpoint."""
    if not url:
        return False
    return any(p.search(url) for p in _INTERNAL_PATTERNS)


def canonicalize_zennify_url(url: str | None, site_url: str | None) -> str:
    """Return the user-facing canonical URL for a Site Mirror response.

    If the input URL is internal (mirror doc / Apps Script), return the
    accompanying site_url (the sites.google.com/zennify.com/... URL).
    If site_url is also internal or missing, return an empty string so the
    Skill drops the citation entirely.
    """
    if url and not looks_like_internal_url(url):
        return url
    if site_url and not looks_like_internal_url(site_url):
        return site_url
    return ""
