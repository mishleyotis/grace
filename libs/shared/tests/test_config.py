"""Tests for ServiceConfig."""


import pytest
from grace_shared.config import ServiceConfig


def test_short_bearer_rejected(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "short")
    with pytest.raises(RuntimeError, match="too short"):
        ServiceConfig.from_env("svc")


def test_missing_bearer_rejected(monkeypatch):
    monkeypatch.delenv("MCP_BEARER_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        ServiceConfig.from_env("svc")


def test_valid_bearer_accepted(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "a" * 32)
    monkeypatch.setenv("GCP_PROJECT", "test-proj")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    cfg = ServiceConfig.from_env("svc")
    assert cfg.name == "svc"
    assert cfg.bearer_token == "a" * 32
    assert cfg.gcp_project == "test-proj"
    assert cfg.log_level == "DEBUG"


def test_defaults(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "a" * 32)
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    cfg = ServiceConfig.from_env("svc")
    assert cfg.gcp_project == ""
    assert cfg.log_level == "INFO"
