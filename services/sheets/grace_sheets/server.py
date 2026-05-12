"""FastMCP server entry point for grace-sheets."""

from __future__ import annotations

from grace_shared.app import build_app
from grace_shared.config import ServiceConfig

from grace_sheets import (
    DRIVE_MAP_SPREADSHEET_ID,
    TRACKER_SPREADSHEET_ID,
    doc_reader,
    drive_map,
    tracker,
)

SERVICE_NAME = "grace-sheets"


def create_app():  # pragma: no cover - exercised at deploy
    from fastmcp import FastMCP  # type: ignore

    from grace_sheets.clients import (
        DriveServiceImpl,
        SheetsChunkReader,
        TrackerServiceImpl,
        build_drive_service,
        build_sheets_service,
    )

    config = ServiceConfig.from_env(SERVICE_NAME)
    sheets = build_sheets_service()
    drive = build_drive_service()

    chunk_reader = SheetsChunkReader(sheets, DRIVE_MAP_SPREADSHEET_ID)
    drive_impl = DriveServiceImpl(drive)
    tracker_impl = TrackerServiceImpl(sheets, TRACKER_SPREADSHEET_ID)

    mcp = FastMCP(SERVICE_NAME)

    @mcp.tool()
    async def drive_map_read_chunk(chunk_index: int) -> dict:
        return drive_map.read_chunk(chunk_reader, chunk_index)

    @mcp.tool()
    async def drive_map_search(query: str, limit: int = 10) -> dict:
        return drive_map.search(chunk_reader, query, limit=limit)

    @mcp.tool()
    async def drive_doc_read(file_id: str, max_chars: int = 30000) -> dict:
        return doc_reader.read_doc(drive_impl, file_id, max_chars)

    @mcp.tool()
    async def drive_doc_read_section(
        file_id: str, section_query: str, context_paragraphs: int = 2
    ) -> dict:
        return doc_reader.read_doc_section(
            drive_impl, file_id, section_query, context_paragraphs
        )

    @mcp.tool()
    async def tracker_get_trainee_tab(trainee_email: str) -> dict:
        return tracker.get_trainee_tab(tracker_impl, trainee_email)

    @mcp.tool()
    async def tracker_create_trainee_tab(
        trainee_email: str,
        full_name: str = "",
        cohort: str = "",
        start_date: str = "",
    ) -> dict:
        return tracker.create_trainee_tab(
            tracker_impl, trainee_email, full_name, cohort, start_date
        )

    @mcp.tool()
    async def tracker_record_lesson_progress(
        trainee_email: str,
        lesson_id: str,
        lesson_name: str,
        status: str = "completed",
        notes: str = "",
    ) -> dict:
        return tracker.record_lesson_progress(
            tracker_impl, trainee_email, lesson_id, lesson_name, status, notes
        )

    @mcp.tool()
    async def tracker_record_quiz_result(
        trainee_email: str,
        module: str,
        score: int,
        max_score: int,
        passed: bool | None = None,
        notes: str = "",
    ) -> dict:
        return tracker.record_quiz_result(
            tracker_impl, trainee_email, module, score, max_score, passed, notes
        )

    return build_app(mcp, name=SERVICE_NAME, config=config)


if __name__ == "__main__":  # pragma: no cover
    import os

    import uvicorn  # type: ignore

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
