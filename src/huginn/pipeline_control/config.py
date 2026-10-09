"""Deployment policy. No connections or migrations during construction."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineControlConfig:
    database_url: str = field(repr=False)
    poll_seconds: float = 2
    heartbeat_seconds: float = 15
    stale_after_seconds: int = 60
    termination_grace_seconds: float = 5

    @classmethod
    def from_env(cls) -> PipelineControlConfig:
        database_url = os.environ.get("HUGINN_DATABASE_URL")
        if not database_url:
            raise RuntimeError("HUGINN_DATABASE_URL is required")
        return cls(database_url)
