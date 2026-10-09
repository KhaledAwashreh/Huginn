"""Narrow owner-specific summary from the durable managed run projection."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    state: str
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cutoff: datetime
    as_of: datetime
    tracking_stale: bool
    strategies_evaluated: int | None
    strategies_skipped: int | None
    created_matches_count: int | None
    existing_matches_skipped_count: int | None
