"""Stress tests SH-S1, SH-S2, SH-S3, SH-S4, SH-S20 for the Drive Map layer."""

from __future__ import annotations

import time

from grace_sheets import drive_map
from grace_sheets.drive_map import _normalize_row, score_row
from sh_helpers import FakeChunkReader, iso_days_ago, make_row


def test_ZS_prefix_bonus_dominates_name_match():
    """SH-S3: ZS_ prefix wins over a +50 name word match."""
    zs_row = _normalize_row(make_row(
        name="ZS_Other",
        summary="kickoff considerations",
        url="https://x/zs",
    ))
    other = _normalize_row(make_row(
        name="Random Kickoff Doc",
        summary="",
        url="https://x/other",
    ))
    s_zs = score_row(zs_row, "kickoff")
    s_other = score_row(other, "kickoff")
    # ZS_ gets +100 (prefix) +10 (summary) = 110; the other gets +50 name word match
    assert s_zs > s_other


def test_recency_tiebreaker():
    """SH-S4."""
    recent = _normalize_row(
        make_row(
            name="ZS_Recent",
            summary="kickoff",
            url="https://x/r",
            modified=iso_days_ago(1),
        )
    )
    old = _normalize_row(
        make_row(
            name="ZS_Old",
            summary="kickoff",
            url="https://x/o",
            modified=iso_days_ago(2000),
        )
    )
    s_recent = score_row(recent, "kickoff")
    s_old = score_row(old, "kickoff")
    assert s_recent > s_old


def test_folders_skipped():
    rows = [
        make_row(name="ZS_Folder", url="https://x/f", is_folder=True),
        make_row(name="ZS_RealDoc", summary="kickoff", url="https://x/d"),
    ]
    out = drive_map.rank_rows(rows, "kickoff")
    assert all(r["name"] != "ZS_Folder" for r in out)


def test_search_succeeds_when_one_chunk_fails(chunk_reader: FakeChunkReader):
    """SH-S2: one chunk fails, search continues."""
    chunk_reader._chunks["A1:M150"] = [
        make_row(name="header", url="", modified=""),  # header stripped
        make_row(name="ZS_Kickoff_Charter", summary="kickoff agenda", url="https://x/a"),
    ]
    chunk_reader._chunks["A151:M300"] = []  # will fail
    chunk_reader._chunks["A301:M400"] = [
        make_row(name="ZS_Late_Kickoff", summary="kickoff post", url="https://x/c"),
    ]
    chunk_reader.fail_ranges = {"A151:M300"}

    out = drive_map.search(chunk_reader, "kickoff")
    names = [r["name"] for r in out["results"]]
    assert "ZS_Kickoff_Charter" in names
    assert "ZS_Late_Kickoff" in names
    assert any("chunk 1 failed" in w for w in out["warnings"])


def test_search_empty_query_validation():
    cr = FakeChunkReader()
    out = drive_map.search(cr, "  ")
    assert out["error"] == "validation_error"


def test_search_clamps_limit():
    cr = FakeChunkReader(
        {
            "A1:M150": [["header"] * 13]
            + [make_row(name=f"ZS_doc_{i}", summary="kickoff x", url=f"https://x/{i}") for i in range(60)],
            "A151:M300": [],
            "A301:M400": [],
        }
    )
    out = drive_map.search(cr, "kickoff", limit=999)
    assert out["status"] == "ok"
    assert len(out["results"]) <= 50


def test_read_chunk_header_strip_only_on_chunk_zero(chunk_reader: FakeChunkReader):
    chunk_reader._chunks["A1:M150"] = [
        ["A", "B", "Name", "", "", "", "", "", "I", "", "K", "L", "M"],
        make_row(name="Row1", url="https://x/1"),
    ]
    chunk_reader._chunks["A151:M300"] = [
        make_row(name="Row2", url="https://x/2"),
    ]
    r0 = drive_map.read_chunk(chunk_reader, 0)
    r1 = drive_map.read_chunk(chunk_reader, 1)
    assert r0["row_count"] == 1
    assert r1["row_count"] == 1


def test_read_chunk_invalid_index():
    cr = FakeChunkReader()
    out = drive_map.read_chunk(cr, 5)
    assert out["error"] == "validation_error"


def test_read_chunk_upstream_failure_isolated(chunk_reader: FakeChunkReader):
    chunk_reader.fail_ranges = {"A1:M150"}
    out = drive_map.read_chunk(chunk_reader, 0)
    assert out["error"] == "upstream_error"


def test_SH_S20_row_count_no_double_count(chunk_reader: FakeChunkReader):
    """All 3 chunks read; no row appears twice in search results."""
    chunk_reader._chunks["A1:M150"] = [["hdr"] * 13] + [
        make_row(name=f"ZS_Doc_A_{i}", summary="kickoff", url=f"https://x/a/{i}")
        for i in range(149)
    ]
    chunk_reader._chunks["A151:M300"] = [
        make_row(name=f"ZS_Doc_B_{i}", summary="kickoff", url=f"https://x/b/{i}")
        for i in range(150)
    ]
    chunk_reader._chunks["A301:M400"] = [
        make_row(name=f"ZS_Doc_C_{i}", summary="kickoff", url=f"https://x/c/{i}")
        for i in range(60)
    ]
    out = drive_map.search(chunk_reader, "kickoff", limit=50)
    names = [r["name"] for r in out["results"]]
    assert len(names) == len(set(names))  # no duplicates


def test_SH_S1_cold_start_performance(chunk_reader: FakeChunkReader):
    """SH-S1: first call < 5s. Sanity check — the in-memory reader is instant."""
    chunk_reader._chunks["A1:M150"] = [["hdr"] * 13] + [
        make_row(name=f"ZS_D_{i}", summary="kickoff", url=f"https://x/{i}")
        for i in range(149)
    ]
    start = time.monotonic()
    out = drive_map.search(chunk_reader, "kickoff")
    elapsed = time.monotonic() - start
    assert out["status"] == "ok"
    assert elapsed < 5.0
