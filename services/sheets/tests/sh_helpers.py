"""Sheets test fixtures: in-memory chunk reader + fake drive + fake tracker."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from grace_sheets.doc_reader import DriveService
from grace_sheets.tracker import TrackerService


def iso_days_ago(days: int) -> str:
    ts = datetime.now(timezone.utc) - timedelta(days=days)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_row(
    *,
    name: str,
    summary: str = "",
    keywords: str = "",
    url: str = "",
    modified: str | None = None,
    is_folder: bool = False,
    level: str = "L1",
) -> list[str]:
    return [
        level,
        "folder" if is_folder else "file",
        name,
        "",  # D
        "",  # E
        "",  # F
        "",  # G
        "",  # H
        modified or iso_days_ago(120),
        "",  # J
        url,
        summary,
        keywords,
    ]


class FakeChunkReader:
    """Maps the 3 expected A1 ranges to fixture row-lists. Optional injected failures."""

    def __init__(self, chunks: dict[str, list[list[str]]] | None = None) -> None:
        self._chunks = chunks or {
            "A1:M150": [],
            "A151:M300": [],
            "A301:M400": [],
        }
        self.fail_ranges: set[str] = set()
        self.calls: list[str] = []

    def __call__(self, range_a1: str) -> list[list[str]]:
        self.calls.append(range_a1)
        if range_a1 in self.fail_ranges:
            raise RuntimeError(f"injected failure on {range_a1}")
        return list(self._chunks.get(range_a1, []))


class FakeDrive(DriveService):
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}

    def add_file(
        self,
        file_id: str,
        *,
        name: str,
        mime_type: str,
        content: bytes,
        web_view: str | None = None,
    ) -> None:
        self.files[file_id] = {
            "name": name,
            "mimeType": mime_type,
            "webViewLink": web_view or f"https://drive.google.com/file/d/{file_id}/view",
            "content": content,
        }

    def get_metadata(self, file_id: str) -> dict:
        if file_id not in self.files:
            from grace_shared.errors import NotFoundError

            raise NotFoundError(f"file_id {file_id!r} not found")
        f = self.files[file_id]
        return {
            "id": file_id,
            "name": f["name"],
            "mimeType": f["mimeType"],
            "webViewLink": f["webViewLink"],
        }

    def export(self, file_id: str, *, mime_type: str) -> bytes:
        return self.files[file_id]["content"]

    def get_media(self, file_id: str) -> bytes:
        return self.files[file_id]["content"]


class FakeTracker(TrackerService):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tabs: dict[str, list[list[Any]]] = {}
        self.add_calls = 0
        self.append_calls: list[tuple[str, list[Any]]] = []
        self.write_calls: list[tuple[str, str, list[list[Any]]]] = []
        self.fail_on_add = False
        self.fail_on_list = False
        self.permission_error = False

    def list_tabs(self) -> list[str]:
        if self.fail_on_list:
            from grace_shared.errors import UpstreamError

            raise UpstreamError("list_tabs upstream failure")
        if self.permission_error:
            from grace_shared.errors import UpstreamError

            raise UpstreamError("permission denied")
        return list(self.tabs.keys())

    def add_tab(self, name: str) -> None:
        with self._lock:
            if self.fail_on_add:
                from grace_shared.errors import UpstreamError

                raise UpstreamError("addSheet failed")
            self.add_calls += 1
            self.tabs[name] = []

    def write_range(self, tab_name: str, range_: str, values: list[list[Any]]) -> None:
        self.write_calls.append((tab_name, range_, values))
        with self._lock:
            for row in values:
                self.tabs.setdefault(tab_name, []).append(row)

    def append_row(self, tab_name: str, values: list[Any]) -> None:
        if self.permission_error:
            from grace_shared.errors import UpstreamError

            raise UpstreamError("permission denied")
        with self._lock:
            self.append_calls.append((tab_name, values))
            self.tabs.setdefault(tab_name, []).append(values)

    def read_tab(self, tab_name: str) -> list[list[Any]]:
        with self._lock:
            return list(self.tabs.get(tab_name, []))


@pytest.fixture
def chunk_reader() -> FakeChunkReader:
    return FakeChunkReader()


@pytest.fixture
def fake_drive() -> FakeDrive:
    return FakeDrive()


@pytest.fixture
def fake_tracker() -> FakeTracker:
    return FakeTracker()
