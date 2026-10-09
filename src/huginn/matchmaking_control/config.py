"""Inert deployment policy for the dedicated matching worker."""

from dataclasses import dataclass, field

from huginn.matchmaking.config import MatchmakingConfig


@dataclass(frozen=True)
class MatchmakingControlConfig:
    database_url: str = field(repr=False)
    poll_seconds: float = 2
    heartbeat_seconds: float = 15
    stale_after_seconds: int = 60
    termination_grace_seconds: float = 5

    @classmethod
    def from_env(cls):
        return cls(MatchmakingConfig.from_env().database_url)
