"""Stress tests SH-S5..SH-S12, SH-DR1..SH-DR5 for the Drive doc reader."""

from __future__ import annotations

from grace_sheets.doc_reader import (
    MAX_CHARS_CEILING,
    MAX_CONTEXT_PARAGRAPHS,
    read_doc,
    read_doc_section,
)
from sh_helpers import FakeDrive


def test_SH_S5_read_google_doc(fake_drive: FakeDrive):
    fid = "1AAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    fake_drive.add_file(
        fid,
        name="ZS_Kickoff",
        mime_type="application/vnd.google-apps.document",
        content=b"This is the kickoff document.\n\nIt has multiple paragraphs.",
    )
    out = read_doc(fake_drive, fid)
    assert out["status"] == "ok"
    assert "kickoff document" in out["text"]
    assert out["mime_type"] == "text/plain"
    assert out["char_count"] == len(out["text"])


def test_SH_S6_read_google_sheet_csv(fake_drive: FakeDrive):
    fid = "1BBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
    fake_drive.add_file(
        fid,
        name="ZS_Tracker",
        mime_type="application/vnd.google-apps.spreadsheet",
        content=b"col1,col2,col3\na,b,c\nd,e,f\n",
    )
    out = read_doc(fake_drive, fid)
    assert out["status"] == "ok"
    assert out["mime_type"] == "text/csv"
    assert "col1,col2,col3" in out["text"]


def test_SH_S7_truncation(fake_drive: FakeDrive):
    fid = "1CCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
    big = ("X" * 50_000).encode()
    fake_drive.add_file(
        fid,
        name="Big",
        mime_type="application/vnd.google-apps.document",
        content=big,
    )
    out = read_doc(fake_drive, fid, max_chars=1000)
    assert out["truncated"] is True
    assert out["char_count"] == 1000
    assert len(out["text"]) == 1000


def test_SH_S8_clamp_to_ceiling(fake_drive: FakeDrive):
    fid = "1DDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
    big = ("Y" * (MAX_CHARS_CEILING + 5000)).encode()
    fake_drive.add_file(
        fid,
        name="Big",
        mime_type="application/vnd.google-apps.document",
        content=big,
    )
    out = read_doc(fake_drive, fid, max_chars=999_999)
    assert out["char_count"] == MAX_CHARS_CEILING
    assert out["truncated"] is True


def test_SH_S9_non_text_mime(fake_drive: FakeDrive):
    fid = "1EEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
    fake_drive.add_file(
        fid,
        name="vid",
        mime_type="video/mp4",
        content=b"\x00\x00\x00",
        web_view="https://drive.google.com/file/d/vidvid/view",
    )
    out = read_doc(fake_drive, fid)
    assert out["error"] == "validation_error"
    assert out["webViewLink"]


def test_SH_S10_not_found(fake_drive: FakeDrive):
    out = read_doc(fake_drive, "1XYZ1234567890XYZ12345678")
    assert out["error"] == "not_found"


def test_SH_S11_read_section_finds_heading(fake_drive: FakeDrive):
    fid = "1FFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    body = (
        "# Intro\n\nFront matter goes here.\n\n## Kickoff Phase\n\n"
        "Step 1: Identify the sponsor.\n\nStep 2: Confirm the goals.\n\n"
        "## Closing\n\nWrap-up tasks."
    )
    fake_drive.add_file(
        fid,
        name="ZS_Project Delivery Checklist",
        mime_type="application/vnd.google-apps.document",
        content=body.encode(),
    )
    out = read_doc_section(fake_drive, fid, "kickoff phase", context_paragraphs=2)
    assert out["status"] == "ok"
    assert "Step 1" in out["text"]
    assert "Step 2" in out["text"]


def test_SH_S12_section_no_match(fake_drive: FakeDrive):
    fid = "1FFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    fake_drive.add_file(
        fid,
        name="x",
        mime_type="application/vnd.google-apps.document",
        content=b"# Intro\n\nBody.",
    )
    out = read_doc_section(fake_drive, fid, "nonexistent")
    assert out["status"] == "no_results"
    assert "drive_doc_read" in out["hint"]


def test_SH_DR1_non_utf8_falls_back(fake_drive: FakeDrive):
    fid = "1GGGGGGGGGGGGGGGGGGGGGGGGGGGGG"
    fake_drive.add_file(
        fid,
        name="bad",
        mime_type="text/plain",
        content=b"\xff\xfe Hello",
    )
    out = read_doc(fake_drive, fid)
    assert out["status"] == "ok"
    assert isinstance(out["text"], str)


def test_SH_DR2_empty(fake_drive: FakeDrive):
    fid = "1HHHHHHHHHHHHHHHHHHHHHHHHHHHHH"
    fake_drive.add_file(
        fid,
        name="empty",
        mime_type="application/vnd.google-apps.document",
        content=b"",
    )
    out = read_doc(fake_drive, fid)
    assert out["status"] == "ok"
    assert out["text"] == ""
    assert out["char_count"] == 0
    assert out["truncated"] is False


def test_SH_DR3_pdf_extraction(fake_drive: FakeDrive):
    fid = "1IIIIIIIIIIIIIIIIIIIIIIIIIIIII"
    # Minimal PDF text block sequence the fallback can parse.
    pdf = b"%PDF-1.4\nBT (Hello World) ET\n%%EOF"
    fake_drive.add_file(fid, name="t", mime_type="application/pdf", content=pdf)
    out = read_doc(fake_drive, fid)
    assert out["status"] == "ok"
    assert "Hello" in out["text"]


def test_SH_DR4_url_as_file_id(fake_drive: FakeDrive):
    out = read_doc(fake_drive, "https://docs.google.com/document/d/1abc/edit")
    assert out["error"] == "validation_error"
    assert "looks malformed" in out["message"]


def test_SH_DR5_context_clamped(fake_drive: FakeDrive):
    fid = "1JJJJJJJJJJJJJJJJJJJJJJJJJJJJJ"
    body = "# Section A\n\n" + "\n\n".join(f"Para {i}." for i in range(100))
    fake_drive.add_file(
        fid,
        name="x",
        mime_type="application/vnd.google-apps.document",
        content=body.encode(),
    )
    out = read_doc_section(fake_drive, fid, "section a", context_paragraphs=999)
    assert out["status"] == "ok"
    # Paragraph slice should be bounded by MAX_CONTEXT_PARAGRAPHS
    assert out["paragraph_end"] - out["paragraph_start"] <= MAX_CONTEXT_PARAGRAPHS + 1
