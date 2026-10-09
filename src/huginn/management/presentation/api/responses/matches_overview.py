"""Overview response from owner-wide durable state only."""

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.evaluation_summary import (
    EvaluationSummaryResponse,
)


class MatchesOverviewResponse(ResponseModel):
    has_matches: bool
    has_active_strategies: bool
    latest_evaluation: EvaluationSummaryResponse | None
