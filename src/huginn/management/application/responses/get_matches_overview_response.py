"""Owner-wide match overview returned by the use case."""

from dataclasses import dataclass

from huginn.management.application.read_models.matches_overview import MatchesOverview


@dataclass(frozen=True, slots=True)
class GetMatchesOverviewResponse:
    overview: MatchesOverview
