from typing import Protocol

from huginn.management.domain.value_objects.common import Page
from huginn.matchmaking_control.application.read_models.target_user import TargetUser


class TargetUserQuery(Protocol):
    def search(self, search: str, offset: int, limit: int) -> Page[TargetUser]: ...
    def eligible_count(self) -> int: ...
