"""Authenticated owner-wide overview input."""

from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True, slots=True)
class GetMatchesOverviewRequest:
    principal: Principal
