"""Onboarding Tracker — per-trainee tab management.

Tools:
  tracker_get_trainee_tab(trainee_email)
  tracker_create_trainee_tab(trainee_email, full_name, cohort, start_date)
  tracker_record_lesson_progress(trainee_email, lesson_id, lesson_name, status, notes)
  tracker_record_quiz_result(trainee_email, module, score, max_score, passed, notes)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from grace_shared.errors import NotFoundError, UpstreamError, ValidationError, to_error_dict

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TAB_NAME_MAX = 100

HEADER_ROWS = (
    ["trainee_email", "full_name", "cohort", "start_date", "created_at"],
    [],  # blank separator
    ["event_type", "lesson_id_or_module", "name", "status_or_score", "max_score", "notes", "ts"],
)


def _validate_email(email: Any) -> str:
    if not isinstance(email, str) or not email.strip():
        raise ValidationError("trainee_email is required")
    e = email.strip()
    if not EMAIL_RE.match(e):
        raise ValidationError(f"trainee_email {e!r} is not a valid email")
    return e.lower()


def _tab_name_from_email(email: str) -> str:
    name = email.lower()
    if len(name) > TAB_NAME_MAX:
        raise ValidationError("email too long for a tab name")
    return name


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TrackerService:
    """Interface the tools call. Real impl wraps Sheets v4 batchUpdate / values.append."""

    def list_tabs(self) -> list[str]:
        raise NotImplementedError

    def add_tab(self, name: str) -> None:
        raise NotImplementedError

    def write_range(self, tab_name: str, range_: str, values: list[list[Any]]) -> None:
        raise NotImplementedError

    def append_row(self, tab_name: str, values: list[Any]) -> None:
        raise NotImplementedError

    def read_tab(self, tab_name: str) -> list[list[Any]]:
        raise NotImplementedError


def get_trainee_tab(service: TrackerService, trainee_email: Any) -> dict:
    try:
        email = _validate_email(trainee_email)
    except ValidationError as exc:
        return to_error_dict(exc)
    tab = _tab_name_from_email(email)
    try:
        tabs = service.list_tabs()
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"list_tabs failed: {exc}"))
    if tab not in tabs:
        return {"status": "not_found", "tab_name": tab, "trainee_email": email}
    try:
        rows = service.read_tab(tab) or []
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"read_tab failed: {exc}"))
    return {
        "status": "ok",
        "tab_name": tab,
        "trainee_email": email,
        "row_count": len(rows),
        "rows": rows,
    }


def create_trainee_tab(
    service: TrackerService,
    trainee_email: Any,
    full_name: Any = "",
    cohort: Any = "",
    start_date: Any = "",
) -> dict:
    try:
        email = _validate_email(trainee_email)
    except ValidationError as exc:
        return to_error_dict(exc)
    tab = _tab_name_from_email(email)
    try:
        tabs = service.list_tabs()
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"list_tabs failed: {exc}"))
    if tab in tabs:
        return {"status": "exists", "tab_name": tab, "trainee_email": email}
    try:
        service.add_tab(tab)
        header = [
            ["trainee_email", "full_name", "cohort", "start_date", "created_at"],
            [email, str(full_name or ""), str(cohort or ""), str(start_date or ""), _now_iso()],
            [],
            [
                "event_type",
                "lesson_id_or_module",
                "name",
                "status_or_score",
                "max_score",
                "notes",
                "ts",
            ],
        ]
        service.write_range(tab, "A1:G4", header)
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"create tab failed: {exc}"))
    return {"status": "created", "tab_name": tab, "trainee_email": email}


def _require_tab(service: TrackerService, email: str) -> str:
    tab = _tab_name_from_email(email)
    tabs = service.list_tabs()
    if tab not in tabs:
        raise NotFoundError(
            f"tab {tab!r} not found; call tracker_create_trainee_tab first"
        )
    return tab


def record_lesson_progress(
    service: TrackerService,
    trainee_email: Any,
    lesson_id: Any,
    lesson_name: Any,
    status: Any = "completed",
    notes: Any = "",
) -> dict:
    try:
        email = _validate_email(trainee_email)
    except ValidationError as exc:
        return to_error_dict(exc)
    if not isinstance(lesson_id, str) or not lesson_id.strip():
        return to_error_dict(ValidationError("lesson_id is required"))
    if not isinstance(lesson_name, str) or not lesson_name.strip():
        return to_error_dict(ValidationError("lesson_name is required"))
    try:
        tab = _require_tab(service, email)
    except NotFoundError as exc:
        return to_error_dict(exc)
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"list_tabs failed: {exc}"))
    row = [
        "lesson",
        lesson_id.strip(),
        lesson_name.strip(),
        str(status or "completed"),
        "",
        str(notes or ""),
        _now_iso(),
    ]
    try:
        service.append_row(tab, row)
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"tracker append failed: {exc}"))
    return {
        "status": "ok",
        "tab_name": tab,
        "trainee_email": email,
        "row_written": row,
    }


def record_quiz_result(
    service: TrackerService,
    trainee_email: Any,
    module: Any,
    score: Any,
    max_score: Any,
    passed: Any = None,
    notes: Any = "",
) -> dict:
    try:
        email = _validate_email(trainee_email)
    except ValidationError as exc:
        return to_error_dict(exc)
    if not isinstance(module, str) or not module.strip():
        return to_error_dict(ValidationError("module is required"))
    try:
        s = int(score)
        ms = int(max_score)
    except Exception:
        return to_error_dict(ValidationError("score and max_score must be integers"))
    if ms <= 0:
        return to_error_dict(ValidationError("max_score must be > 0"))
    if s < 0:
        return to_error_dict(ValidationError("score must be >= 0"))
    if s > ms:
        return to_error_dict(
            ValidationError(f"score {s} exceeds max_score {ms}")
        )
    if passed is None:
        passed = s / ms >= 0.8

    try:
        tab = _require_tab(service, email)
    except NotFoundError as exc:
        return to_error_dict(exc)
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"list_tabs failed: {exc}"))
    row = [
        "quiz",
        module.strip(),
        "",
        f"{s}",
        f"{ms}",
        str(notes or "") + (f" passed={bool(passed)}" if passed is not None else ""),
        _now_iso(),
    ]
    try:
        service.append_row(tab, row)
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"tracker append failed: {exc}"))
    return {
        "status": "ok",
        "tab_name": tab,
        "trainee_email": email,
        "score": s,
        "max_score": ms,
        "passed": bool(passed),
        "row_written": row,
    }
