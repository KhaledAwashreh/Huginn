"""Owner-wide match and latest managed evaluation summary."""

from dataclasses import dataclass

from huginn.management.application.read_models.evaluation_summary import (
    EvaluationSummary,
)


@dataclass(frozen=True, slots=True)
class MatchesOverview:
    has_matches: bool
    has_active_strategies: bool
    latest_evaluation: EvaluationSummary | None
