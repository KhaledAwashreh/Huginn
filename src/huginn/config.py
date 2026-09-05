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


def load_config() -> Config:
    database_url = os.environ.get("HUGINN_DATABASE_URL")
    if not database_url:
        raise RuntimeError("HUGINN_DATABASE_URL is not set. Copy .env.example to .env.")
    return Config(database_url=database_url)
