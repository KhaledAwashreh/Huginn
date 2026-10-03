"""Ideal client profile persistence contract."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.common import Page
from huginn.management.domain.ideal_client_profile import (
    IdealClientProfile,
    IdealClientProfileChanges,
    NewIdealClientProfile,
)


class IdealClientProfileRepository(Protocol):
    def create(self, profile: NewIdealClientProfile) -> IdealClientProfile: ...
    def get_owned(
        self, user_id: UUID, profile_id: UUID
    ) -> IdealClientProfile | None: ...
    def list_owned(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> Page[IdealClientProfile]: ...
    def update_owned(
        self, user_id: UUID, profile_id: UUID, changes: IdealClientProfileChanges
    ) -> IdealClientProfile | None: ...
    def delete_owned(self, user_id: UUID, profile_id: UUID) -> bool: ...
