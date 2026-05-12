"""Tests for typed errors."""

from grace_shared.errors import NotFoundError, UpstreamError, ValidationError, to_error_dict


def test_validation_error_dict():
    assert to_error_dict(ValidationError("x")) == {
        "error": "validation_error",
        "message": "x",
    }


def test_not_found_error_dict():
    assert to_error_dict(NotFoundError("y")) == {
        "error": "not_found",
        "message": "y",
    }


def test_upstream_error_dict():
    assert to_error_dict(UpstreamError("z")) == {
        "error": "upstream_error",
        "message": "z",
    }
