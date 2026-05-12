"""Env-driven ServiceConfig used by every MCP service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    bearer_token: str
    gcp_project: str
    log_level: str

    @classmethod
    def from_env(cls, name: str) -> "ServiceConfig":
        bearer = os.environ.get("MCP_BEARER_TOKEN", "").strip()
        if len(bearer) < 16:
            raise RuntimeError(
                "MCP_BEARER_TOKEN is missing or too short (need >= 16 chars)"
            )
        return cls(
            name=name,
            bearer_token=bearer,
            gcp_project=os.environ.get("GCP_PROJECT", ""),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
