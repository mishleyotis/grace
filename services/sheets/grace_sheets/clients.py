"""Concrete Google API client wrappers (used by the FastMCP server entry point).

The drive_map / tracker / doc_reader modules accept abstract callables/services
so the deployment-time wiring lives here and unit tests can use plain fakes.
"""

from __future__ import annotations

import threading
from typing import Any

from grace_shared.errors import NotFoundError, UpstreamError


def build_sheets_service():  # pragma: no cover - exercised in deploy
    import google.auth  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def build_drive_service():  # pragma: no cover
    import google.auth  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
        ]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class SheetsChunkReader:  # pragma: no cover
    def __init__(self, sheets_service: Any, spreadsheet_id: str) -> None:
        self._svc = sheets_service
        self._sid = spreadsheet_id

    def __call__(self, range_a1: str) -> list[list[Any]]:
        try:
            resp = (
                self._svc.spreadsheets()
                .values()
                .get(spreadsheetId=self._sid, range=range_a1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"sheets values.get failed: {exc}") from exc
        return resp.get("values", [])


class DriveServiceImpl:  # pragma: no cover
    """Real Drive client used by doc_reader."""

    def __init__(self, drive_service: Any) -> None:
        self._svc = drive_service

    def get_metadata(self, file_id: str) -> dict:
        try:
            return (
                self._svc.files()
                .get(
                    fileId=file_id,
                    fields="id,name,mimeType,webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "404" in msg or "notFound" in msg:
                raise NotFoundError(f"file_id {file_id!r} not found") from exc
            raise UpstreamError(f"drive metadata fetch failed: {exc}") from exc

    def export(self, file_id: str, *, mime_type: str) -> bytes:
        try:
            return self._svc.files().export(fileId=file_id, mimeType=mime_type).execute()
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"drive export failed: {exc}") from exc

    def get_media(self, file_id: str) -> bytes:
        try:
            return (
                self._svc.files()
                .get_media(fileId=file_id, supportsAllDrives=True)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"drive get_media failed: {exc}") from exc


class TrackerServiceImpl:  # pragma: no cover
    def __init__(self, sheets_service: Any, spreadsheet_id: str) -> None:
        self._svc = sheets_service
        self._sid = spreadsheet_id
        self._lock = threading.Lock()

    def list_tabs(self) -> list[str]:
        try:
            meta = (
                self._svc.spreadsheets()
                .get(spreadsheetId=self._sid, fields="sheets.properties.title")
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"tracker get failed: {exc}") from exc
        return [s["properties"]["title"] for s in meta.get("sheets", [])]

    def add_tab(self, name: str) -> None:
        with self._lock:
            try:
                self._svc.spreadsheets().batchUpdate(
                    spreadsheetId=self._sid,
                    body={"requests": [{"addSheet": {"properties": {"title": name}}}]},
                ).execute()
            except Exception as exc:  # noqa: BLE001
                raise UpstreamError(f"tracker addSheet failed: {exc}") from exc

    def write_range(self, tab_name: str, range_: str, values: list[list[Any]]) -> None:
        try:
            self._svc.spreadsheets().values().update(
                spreadsheetId=self._sid,
                range=f"'{tab_name}'!{range_}",
                valueInputOption="RAW",
                body={"values": values},
            ).execute()
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"tracker write failed: {exc}") from exc

    def append_row(self, tab_name: str, values: list[Any]) -> None:
        try:
            self._svc.spreadsheets().values().append(
                spreadsheetId=self._sid,
                range=f"'{tab_name}'!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [values]},
            ).execute()
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"tracker append failed: {exc}") from exc

    def read_tab(self, tab_name: str) -> list[list[Any]]:
        try:
            resp = (
                self._svc.spreadsheets()
                .values()
                .get(spreadsheetId=self._sid, range=f"'{tab_name}'!A1:Z1000")
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"tracker read failed: {exc}") from exc
        return resp.get("values", [])
