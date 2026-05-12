"""Shared fixtures for site-mirror tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import pytest
from grace_site_mirror.client import AppsScriptClient


@dataclass
class FakeResponse:
    status_code: int = 200
    headers: dict = field(default_factory=lambda: {"content-type": "application/json"})
    _body: Any = field(default_factory=dict)
    text: str = ""

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeHttpClient:
    """Lightweight stand-in for httpx.AsyncClient."""

    def __init__(
        self,
        handler: Callable[[str, dict], FakeResponse] | FakeResponse | Exception,
    ) -> None:
        self.handler = handler
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url: str, params: dict | None = None) -> FakeResponse:
        self.calls.append((url, params or {}))
        if isinstance(self.handler, Exception):
            raise self.handler
        if callable(self.handler):
            return self.handler(url, params or {})
        return self.handler

    async def aclose(self) -> None:
        return None


@pytest.fixture
def make_client():
    def _make(handler) -> AppsScriptClient:
        return AppsScriptClient(
            "https://script.google.com/macros/s/AKfycb_TEST/exec",
            http_client=FakeHttpClient(handler),
        )

    return _make


def json_response(body: Any, status: int = 200) -> FakeResponse:
    return FakeResponse(status_code=status, _body=body, text=json.dumps(body))
