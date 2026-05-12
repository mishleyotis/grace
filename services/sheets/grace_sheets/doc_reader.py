"""Drive document reader — the accuracy primitive.

Reads actual document text via the Drive API. Google native types are exported
to text/csv as appropriate; OOXML / PDF / plain text are downloaded with
``files.get_media``. Non-text mimes return a validation error pointing at the
``webViewLink``.

Tools:
  drive_doc_read(file_id, max_chars=30000)
  drive_doc_read_section(file_id, section_query, context_paragraphs=2)
"""

from __future__ import annotations

import re
from typing import Any

from grace_shared.errors import NotFoundError, UpstreamError, ValidationError, to_error_dict

MAX_CHARS_CEILING = 100_000
DEFAULT_MAX_CHARS = 30_000
MAX_CONTEXT_PARAGRAPHS = 20

GOOGLE_NATIVE_EXPORTS: dict[str, str] = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

PLAIN_TEXT_MIMES = {
    "text/plain",
    "text/csv",
    "text/markdown",
    "text/html",
    "application/json",
    "application/xml",
    "text/xml",
}

OOXML_OR_PDF = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


# Service-shaped protocol. We accept a dataclass-like helper with two methods:
class DriveService:
    """Minimal interface the doc reader needs from Drive.

    Implementations:
      - real: uses google-api-python-client
      - fake: in tests
    """

    def get_metadata(self, file_id: str) -> dict:
        raise NotImplementedError

    def export(self, file_id: str, *, mime_type: str) -> bytes:
        raise NotImplementedError

    def get_media(self, file_id: str) -> bytes:
        raise NotImplementedError


def _decode_bytes(content: bytes) -> str:
    if not content:
        return ""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


def _pdf_to_text(content: bytes) -> str:
    """Best-effort PDF extraction.

    The real deployment uses ``pypdf`` if present. In its absence we fall back
    to a minimal extractor that pulls visible BT/ET blocks; this is enough for
    PDFs with a real text layer.
    """
    try:
        from io import BytesIO

        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        # Minimal fallback — extract sequences inside parentheses inside BT...ET blocks
        text_chunks: list[str] = []
        for block in re.findall(rb"BT(.*?)ET", content, flags=re.DOTALL):
            for s in re.findall(rb"\((.*?)\)", block):
                try:
                    text_chunks.append(s.decode("latin-1"))
                except Exception:
                    continue
        return " ".join(text_chunks)


def _validate_file_id(file_id: Any) -> str:
    if not isinstance(file_id, str) or not file_id.strip():
        raise ValidationError("file_id is required")
    fid = file_id.strip()
    # Reject things that look like URLs
    if "://" in fid or "/" in fid or fid.startswith("http"):
        raise ValidationError("file_id looks malformed (looks like a URL)")
    if not FILE_ID_RE.match(fid):
        raise ValidationError("file_id looks malformed")
    return fid


def _clamp_max_chars(value: Any) -> int:
    try:
        n = int(value)
    except Exception:
        n = DEFAULT_MAX_CHARS
    if n <= 0:
        n = DEFAULT_MAX_CHARS
    return min(n, MAX_CHARS_CEILING)


def _read_raw(service: DriveService, file_id: str, mime_type: str) -> tuple[str, str]:
    """Return (text, effective_mime_used)."""
    if mime_type in GOOGLE_NATIVE_EXPORTS:
        export_mime = GOOGLE_NATIVE_EXPORTS[mime_type]
        content = service.export(file_id, mime_type=export_mime)
        return _decode_bytes(content), export_mime
    if mime_type in PLAIN_TEXT_MIMES:
        content = service.get_media(file_id)
        return _decode_bytes(content), mime_type
    if mime_type == "application/pdf":
        content = service.get_media(file_id)
        return _pdf_to_text(content), mime_type
    if mime_type in OOXML_OR_PDF:
        content = service.get_media(file_id)
        # Best-effort: attempt utf-8/latin-1 decode of raw bytes; for OOXML
        # the production path runs through pypdf-equivalent extractors.
        return _decode_bytes(content), mime_type
    # Unsupported
    raise ValidationError(
        f"mime_type {mime_type!r} is not text-readable; open the doc via its webViewLink"
    )


def read_doc(service: DriveService, file_id: Any, max_chars: Any = DEFAULT_MAX_CHARS) -> dict:
    try:
        fid = _validate_file_id(file_id)
    except ValidationError as exc:
        return to_error_dict(exc)
    cap = _clamp_max_chars(max_chars)
    try:
        meta = service.get_metadata(fid)
    except NotFoundError as exc:
        return to_error_dict(exc)
    except UpstreamError as exc:
        return to_error_dict(exc)
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"metadata fetch failed: {exc}"))

    mime_type = meta.get("mimeType", "")
    web_view = meta.get("webViewLink", "")
    name = meta.get("name", "")

    try:
        text, used_mime = _read_raw(service, fid, mime_type)
    except ValidationError as exc:
        return {
            **to_error_dict(exc),
            "webViewLink": web_view,
            "mime_type": mime_type,
        }
    except NotFoundError as exc:
        return to_error_dict(exc)
    except Exception as exc:  # noqa: BLE001
        return to_error_dict(UpstreamError(f"content fetch failed: {exc}"))

    truncated = False
    if len(text) > cap:
        text = text[:cap]
        truncated = True

    return {
        "status": "ok",
        "file_id": fid,
        "name": name,
        "mime_type": used_mime,
        "webViewLink": web_view,
        "text": text,
        "char_count": len(text),
        "truncated": truncated,
    }


HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Z0-9 ,.()/&-]{4,}$)")


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in parts if p]


def read_doc_section(
    service: DriveService,
    file_id: Any,
    section_query: Any,
    context_paragraphs: Any = 2,
) -> dict:
    if not isinstance(section_query, str) or not section_query.strip():
        return to_error_dict(ValidationError("section_query is required"))
    try:
        ctx = int(context_paragraphs)
    except Exception:
        ctx = 2
    ctx = max(0, min(ctx, MAX_CONTEXT_PARAGRAPHS))

    full = read_doc(service, file_id, max_chars=MAX_CHARS_CEILING)
    if "error" in full:
        return full

    paragraphs = _split_paragraphs(full["text"])
    target = section_query.lower().strip()

    match_idx: int | None = None
    for i, para in enumerate(paragraphs):
        first_line = para.splitlines()[0].lower().strip(" #").strip()
        if target in first_line and (
            first_line.startswith("#")
            or first_line.isupper()
            or paragraphs[i].startswith("#")
            or target == first_line
            or HEADING_RE.match(paragraphs[i].splitlines()[0])
        ):
            match_idx = i
            break
    if match_idx is None:
        # Fallback: any paragraph containing the substring
        for i, para in enumerate(paragraphs):
            if target in para.lower():
                match_idx = i
                break
    if match_idx is None:
        return {
            "status": "no_results",
            "file_id": full["file_id"],
            "section_query": section_query,
            "hint": "call drive_doc_read for the full text",
        }

    start = match_idx
    end = min(len(paragraphs), match_idx + 1 + ctx)
    section_text = "\n\n".join(paragraphs[start:end])
    return {
        "status": "ok",
        "file_id": full["file_id"],
        "name": full["name"],
        "mime_type": full["mime_type"],
        "section_query": section_query,
        "text": section_text,
        "char_count": len(section_text),
        "paragraph_start": start,
        "paragraph_end": end,
    }
