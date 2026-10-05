"""Ideal client profile persistence contract."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.value_objects.common import Page
from huginn.management.domain.value_objects.ideal_client_profile import (
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
