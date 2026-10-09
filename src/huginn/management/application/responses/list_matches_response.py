"""Match page returned by the list use case."""

from dataclasses import dataclass

from huginn.management.application.read_models.user_match import UserMatch
from huginn.management.domain.value_objects.common import Page


@dataclass(frozen=True, slots=True)
class ListMatchesResponse:
    page: Page[UserMatch]
