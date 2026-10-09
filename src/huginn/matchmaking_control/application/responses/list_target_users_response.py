from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Page
from huginn.matchmaking_control.application.read_models.target_user import TargetUser


@dataclass(frozen=True)
class ListTargetUsersResponse:
    page: Page[TargetUser]
    total_eligible_count: int
