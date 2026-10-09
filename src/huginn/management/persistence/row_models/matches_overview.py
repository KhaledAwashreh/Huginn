"""Strict database boundary for the owner-wide Matches overview."""

from pydantic import BaseModel, ConfigDict


class MatchesOverviewRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    has_matches: bool
    has_active_strategies: bool
