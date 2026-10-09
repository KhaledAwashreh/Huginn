from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Page
from huginn.matchmaking_control.application.read_models.run_summary import RunSummary


@dataclass(frozen=True)
class ListRunsResponse:
    page: Page[RunSummary]
