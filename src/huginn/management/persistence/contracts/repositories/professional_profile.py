"""Professional profile persistence contract."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.professional_profile import ProfessionalProfile
from huginn.management.domain.value_objects.professional_profile import (
    NewProfessionalProfile,
    ProfessionalProfileChanges,
)


class ProfessionalProfileRepository(Protocol):
    def get_owned(self, user_id: UUID) -> ProfessionalProfile | None: ...
    def create(self, profile: NewProfessionalProfile) -> ProfessionalProfile: ...
    def update(
        self, user_id: UUID, changes: ProfessionalProfileChanges
    ) -> ProfessionalProfile | None: ...
