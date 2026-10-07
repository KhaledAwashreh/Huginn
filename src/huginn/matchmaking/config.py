"""Inert runtime configuration, matchmaking design section 9."""

import os
from dataclasses import dataclass

from psycopg.conninfo import conninfo_to_dict

from huginn.matchmaking.application.errors.execution import ConfigurationError


@dataclass(frozen=True)
class MatchmakingConfig:
    database_url: str

    def __post_init__(self) -> None:
        if type(self.database_url) is not str or not self.database_url.strip():
            raise ConfigurationError("Matchmaking database configuration is required")
        try:
            options = conninfo_to_dict(self.database_url)
        except Exception as exc:
            raise ConfigurationError(
                "Invalid matchmaking database configuration"
            ) from exc
        if not options.get("dbname"):
            raise ConfigurationError("Matchmaking database name is required")

    @classmethod
    def from_env(cls) -> MatchmakingConfig:
        return cls(os.environ.get("HUGINN_MATCHMAKING_DATABASE_URL", ""))
