"""Owner-specific durable evaluation summary."""

from datetime import datetime
from typing import Literal

from huginn.management.presentation.api.responses.common import ResponseModel

EvaluationState = Literal[
    "pending",
    "running",
    "succeeded",
    "disabled_user",
    "user_not_found",
    "failed",
    "commit_outcome_unknown",
    "not_executed",
]


class EvaluationSummaryResponse(ResponseModel):
    state: EvaluationState
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
