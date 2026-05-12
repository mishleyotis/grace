"""Apps Script client — wraps the SiteMirrorQuery web app over HTTPS.

Failure mapping:
  - timeout / network errors  -> UpstreamError('request failed: ...')
  - non-2xx HTTP              -> UpstreamError('Apps Script returned HTTP <n>: ...')
  - non-JSON content-type     -> UpstreamError('non-JSON content-type')
  - malformed JSON body       -> UpstreamError('malformed JSON: ...')
"""

from __future__ import annotations

import os
from typing import Any

from grace_shared.errors import UpstreamError, ValidationError

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_SEARCH_LIMIT = 50

ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "getSection",
        "searchSections",
        "getURLIndex",
        "getNavMap",
        "getLinkIndex",
    }
)


class AppsScriptClient:
    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: Any | None = None,
    ) -> None:
        if not endpoint:
            raise ValidationError("Apps Script endpoint is empty")
        self._endpoint = endpoint
        self._timeout = timeout
        self._http_client = http_client  # injectable for tests

    async def call(self, action: str, params: dict | None = None) -> dict | list:
        if action not in ALLOWED_ACTIONS:
            raise ValidationError(f"unknown Apps Script action: {action}")

        query: dict[str, str] = {"action": action}
        if params:
            for k, v in params.items():
                if v is None:
                    continue
                query[k] = str(v)

        client = self._http_client
        owns_client = False
        if client is None:
            import httpx  # type: ignore

            client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
            owns_client = True

        try:
            try:
                resp = await client.get(self._endpoint, params=query)
            except Exception as exc:  # network / timeout
                raise UpstreamError(f"request failed: {exc}") from exc

            if resp.status_code >= 400:
                raise UpstreamError(
                    f"Apps Script returned HTTP {resp.status_code}: {resp.text[:200]}"
                )

            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype.lower():
                raise UpstreamError("non-JSON content-type")

            try:
                return resp.json()
            except Exception as exc:
                raise UpstreamError(f"malformed JSON: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()


def get_endpoint_from_env() -> str:
    endpoint = os.environ.get("APPS_SCRIPT_URL", "").strip()
    if not endpoint:
        raise RuntimeError("APPS_SCRIPT_URL env var is required")
    return endpoint
