"""Stress tests SH-S13..SH-S19 for the Onboarding Tracker."""

from __future__ import annotations

import threading

from grace_sheets.tracker import (
    create_trainee_tab,
    get_trainee_tab,
    record_lesson_progress,
    record_quiz_result,
)
from sh_helpers import FakeTracker


def test_SH_S13_idempotent_create(fake_tracker: FakeTracker):
    out1 = create_trainee_tab(
        fake_tracker, "alice@example.com", full_name="Alice", start_date="2026-05-11"
    )
    assert out1["status"] == "created"
    assert fake_tracker.add_calls == 1
    out2 = create_trainee_tab(
        fake_tracker, "alice@example.com", full_name="Alice", start_date="2026-05-11"
    )
    assert out2["status"] == "exists"
    assert fake_tracker.add_calls == 1  # no second addSheet


def test_SH_S14_lesson_on_missing_tab(fake_tracker: FakeTracker):
    out = record_lesson_progress(
        fake_tracker,
        "alice@example.com",
        lesson_id="L1",
        lesson_name="Discovery",
    )
    assert out["error"] == "not_found"
    assert "tracker_create_trainee_tab" in out["message"]


def test_SH_S15_quiz_score_validation(fake_tracker: FakeTracker):
    create_trainee_tab(fake_tracker, "alice@example.com")
    out = record_quiz_result(
        fake_tracker, "alice@example.com", module="discovery", score=11, max_score=10
    )
    assert out["error"] == "validation_error"
    assert "score 11 exceeds max_score 10" in out["message"]


def test_quiz_pass_default_threshold(fake_tracker: FakeTracker):
    create_trainee_tab(fake_tracker, "alice@example.com")
    out = record_quiz_result(
        fake_tracker, "alice@example.com", module="discovery", score=8, max_score=10
    )
    assert out["status"] == "ok"
    assert out["passed"] is True


def test_quiz_fail_below_threshold(fake_tracker: FakeTracker):
    create_trainee_tab(fake_tracker, "alice@example.com")
    out = record_quiz_result(
        fake_tracker, "alice@example.com", module="discovery", score=5, max_score=10
    )
    assert out["status"] == "ok"
    assert out["passed"] is False


def test_quiz_max_score_zero_rejected(fake_tracker: FakeTracker):
    create_trainee_tab(fake_tracker, "alice@example.com")
    out = record_quiz_result(
        fake_tracker, "alice@example.com", module="x", score=0, max_score=0
    )
    assert out["error"] == "validation_error"


def test_SH_S16_concurrent_writes_preserved(fake_tracker: FakeTracker):
    """10 threads append rows; all 10 land."""
    create_trainee_tab(fake_tracker, "alice@example.com")

    def worker(i: int):
        record_lesson_progress(
            fake_tracker,
            "alice@example.com",
            lesson_id=f"L{i}",
            lesson_name=f"Lesson {i}",
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = fake_tracker.read_tab("alice@example.com")
    lesson_rows = [r for r in rows if r and r[0] == "lesson"]
    assert len(lesson_rows) == 10


def test_SH_S17_email_lowercased(fake_tracker: FakeTracker):
    out = create_trainee_tab(fake_tracker, "Alice@Example.COM", full_name="A")
    assert out["status"] == "created"
    assert out["tab_name"] == "alice@example.com"
    assert "alice@example.com" in fake_tracker.tabs


def test_SH_S18_bad_email_rejected(fake_tracker: FakeTracker):
    out = create_trainee_tab(fake_tracker, "not-an-email")
    assert out["error"] == "validation_error"

    out2 = get_trainee_tab(fake_tracker, "")
    assert out2["error"] == "validation_error"


def test_SH_S19_permission_boundary_propagated(fake_tracker: FakeTracker):
    create_trainee_tab(fake_tracker, "alice@example.com")
    fake_tracker.permission_error = True
    out = record_lesson_progress(
        fake_tracker, "alice@example.com", lesson_id="L1", lesson_name="x"
    )
    assert out["error"] == "upstream_error"
    assert "permission denied" in out["message"]


def test_get_trainee_tab_returns_rows(fake_tracker: FakeTracker):
    create_trainee_tab(
        fake_tracker, "alice@example.com", full_name="Alice", start_date="2026-05-11"
    )
    out = get_trainee_tab(fake_tracker, "alice@example.com")
    assert out["status"] == "ok"
    assert out["row_count"] > 0


def test_get_trainee_tab_not_found(fake_tracker: FakeTracker):
    out = get_trainee_tab(fake_tracker, "ghost@example.com")
    assert out["status"] == "not_found"


def test_lesson_id_required(fake_tracker: FakeTracker):
    create_trainee_tab(fake_tracker, "alice@example.com")
    out = record_lesson_progress(
        fake_tracker, "alice@example.com", lesson_id="", lesson_name="x"
    )
    assert out["error"] == "validation_error"
