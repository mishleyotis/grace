"""Typed exceptions converted to {error, message} dicts at the tool boundary."""

from __future__ import annotations


class GraceError(Exception):
    """Base for all grace exceptions."""

    error_code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(GraceError):
    error_code = "validation_error"


class NotFoundError(GraceError):
    error_code = "not_found"


class UpstreamError(GraceError):
    error_code = "upstream_error"


def to_error_dict(exc: GraceError) -> dict:
    return {"error": exc.error_code, "message": exc.message}
