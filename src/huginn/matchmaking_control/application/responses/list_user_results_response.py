from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Page
from huginn.matchmaking_control.application.read_models.user_result import UserResult


@dataclass(frozen=True)
class ListUserResultsResponse:
    page: Page[UserResult] | None
