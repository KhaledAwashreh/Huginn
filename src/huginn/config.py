"""Configuration loading. See architecture document section 10
(cross-cutting concerns): secrets behind an abstracted provider, local
key vault for now; config format (YAML) not yet chosen. This module is
the abstraction boundary so that choice can change without touching
callers, currently backed by environment variables and a local `.env`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    database_url: str
    yc_algolia_api_key: str


def _require_env(name: str, guidance: str = "") -> str:
    """Read a required variable, or raise naming it and where the value
    should come from.
    """
    value = os.environ.get(name)
    if not value:
        suffix = f" {guidance}" if guidance else ""
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env.{suffix}")
    return value


def load_config() -> Config:
    return Config(
        database_url=_require_env("HUGINN_DATABASE_URL"),
        # Not a secret (shipped to every browser that loads the directory
        # page), but its literal value is not recorded in any tracked doc and
        # can rotate, so it is supplied as config rather than hardcoded. See
        # architecture-notes/yc-fetch-plan.md section 2.
        yc_algolia_api_key=_require_env(
            "HUGINN_YC_ALGOLIA_API_KEY",
            guidance="Fill in YC's current Algolia secured-key blob.",
        ),
    )
