"""Drive Map index — chunked reads + ranked search.

Ranking signals (per design §4.2):
    +100  name starts with ZS_
    +50   per query word: whole-word match in name
    +30   per query word: substring match in name (mutually exclusive with +50)
    +20   per query word: match in keywords (col M)
    +10   per query word: match in summary (col L)
    +10   modified in last 30 days
    +5    modified in last 90 days
    +2    modified in last 365 days

Folders are skipped during search; only files are ranked. Failure isolation:
if one chunk read fails, search continues with the remaining chunks.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from grace_sheets import DRIVE_MAP_CHUNKS, DRIVE_MAP_SPREADSHEET_ID

logger = logging.getLogger("grace.sheets.drive_map")

ROW_LEVEL = 0          # col A
ROW_TYPE = 1           # col B (file vs folder)
ROW_NAME = 2           # col C
ROW_MODIFIED = 8       # col I
ROW_URL = 10           # col K
ROW_SUMMARY = 11       # col L
ROW_KEYWORDS = 12      # col M

ZS_PREFIX = "ZS_"
WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _normalize_row(row: list[Any]) -> list[str]:
    out = [str(x) if x is not None else "" for x in row]
    while len(out) < 13:
        out.append("")
    return out


def _parse_iso_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        # Drive's modifiedTime style — accept both with/without trailing Z
        v = value.replace("Z", "+00:00")
        return datetime.fromisoformat(v)
    except Exception:
        return None


def _recency_bonus(modified: datetime | None, now: datetime | None = None) -> int:
    if not modified:
        return 0
    now = now or datetime.now(timezone.utc)
    if modified.tzinfo is None:
        modified = modified.replace(tzinfo=timezone.utc)
    delta_days = (now - modified).days
    if delta_days < 0:
        delta_days = 0
    if delta_days <= 30:
        return 10
    if delta_days <= 90:
        return 5
    if delta_days <= 365:
        return 2
    return 0


def _tokenize(query: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(query) if len(w) >= 2]


def score_row(row: list[str], query: str, *, now: datetime | None = None) -> int:
    name = row[ROW_NAME]
    keywords = row[ROW_KEYWORDS].lower()
    summary = row[ROW_SUMMARY].lower()
    name_lower = name.lower()
    name_words = set(_tokenize(name))

    score = 0
    if name.startswith(ZS_PREFIX):
        score += 100

    for word in _tokenize(query):
        if word in name_words:
            score += 50
        elif word in name_lower:
            score += 30
        if word in keywords:
            score += 20
        if word in summary:
            score += 10

    modified_at = _parse_iso_date(row[ROW_MODIFIED])
    score += _recency_bonus(modified_at, now=now)
    return score


def _is_folder(row: list[str]) -> bool:
    type_value = row[ROW_TYPE].strip().lower()
    return type_value in {"folder", "folders", "directory"}


def rank_rows(rows: Iterable[list[Any]], query: str, *, limit: int = 10) -> list[dict]:
    scored: list[tuple[int, dict]] = []
    for raw in rows:
        row = _normalize_row(raw)
        if not row[ROW_NAME]:
            continue
        if _is_folder(row):
            continue
        s = score_row(row, query)
        if s <= 0:
            continue
        item = {
            "name": row[ROW_NAME],
            "url": row[ROW_URL],
            "summary": row[ROW_SUMMARY],
            "keywords": row[ROW_KEYWORDS],
            "modified": row[ROW_MODIFIED],
            "score": s,
        }
        scored.append((s, item))
    # Sort by score desc; tie-break by recency desc
    scored.sort(
        key=lambda x: (
            x[0],
            _parse_iso_date(x[1]["modified"]) or datetime.fromtimestamp(0, tz=timezone.utc),
        ),
        reverse=True,
    )
    return [item for _, item in scored[:limit]]


# --------------------------------------------------------------------------
# Tool implementations — take a Sheets client (or callable) for testability.
# --------------------------------------------------------------------------

ChunkReader = Callable[[str], list[list[Any]]]


def read_chunk(reader: ChunkReader, chunk_index: int) -> dict:
    if chunk_index not in (0, 1, 2):
        from grace_shared.errors import ValidationError, to_error_dict

        return to_error_dict(ValidationError("chunk_index must be 0, 1, or 2"))
    rng = DRIVE_MAP_CHUNKS[chunk_index]
    try:
        rows = reader(rng) or []
    except Exception as exc:  # noqa: BLE001
        from grace_shared.errors import UpstreamError, to_error_dict

        return to_error_dict(UpstreamError(f"chunk {chunk_index} read failed: {exc}"))
    if chunk_index == 0 and rows:
        # Strip header row
        rows = rows[1:]
    normalized = [_normalize_row(r) for r in rows]
    return {
        "status": "ok",
        "chunk_index": chunk_index,
        "range": rng,
        "spreadsheet_id": DRIVE_MAP_SPREADSHEET_ID,
        "row_count": len(normalized),
        "rows": normalized,
    }


def search(reader: ChunkReader, query: str, *, limit: int = 10) -> dict:
    from grace_shared.errors import ValidationError, to_error_dict

    if not isinstance(query, str) or not query.strip():
        return to_error_dict(ValidationError("query is required"))
    if not isinstance(limit, int) or limit < 1:
        limit = 10
    limit = min(limit, 50)

    all_rows: list[list[str]] = []
    warnings: list[str] = []
    for idx in range(3):
        try:
            rows = reader(DRIVE_MAP_CHUNKS[idx]) or []
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"chunk {idx} failed: {exc}")
            logger.warning(
                "drive_map chunk %d read failed: %s; continuing", idx, exc
            )
            continue
        if idx == 0 and rows:
            rows = rows[1:]
        all_rows.extend(_normalize_row(r) for r in rows)

    if not all_rows:
        return {
            "status": "no_results",
            "query": query,
            "results": [],
            "warnings": warnings,
        }

    results = rank_rows(all_rows, query, limit=limit)
    if not results:
        return {
            "status": "no_results",
            "query": query,
            "results": [],
            "warnings": warnings,
        }
    return {
        "status": "ok",
        "query": query,
        "results": results,
        "warnings": warnings,
    }
