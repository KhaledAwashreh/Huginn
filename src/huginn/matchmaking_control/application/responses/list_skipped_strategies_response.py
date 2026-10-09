from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Page
from huginn.matchmaking_control.application.read_models.skipped_strategy_result import (
    SkippedStrategyResult,
)


@dataclass(frozen=True)
class ListSkippedStrategiesResponse:
    page: Page[SkippedStrategyResult] | None
