from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.prospect import Prospect


class ProspectRepository(Protocol):
    def get_many_owned(
        self, business_id: UUID, prospect_ids: tuple[UUID, ...]
    ) -> tuple[Prospect, ...]: ...
    def get_owned(self, business_id: UUID, prospect_id: UUID) -> Prospect | None: ...
    def get_by_business_company(
        self, business_id: UUID, company_id: UUID
    ) -> Prospect | None: ...
    def create(self, prospect: Prospect) -> Prospect:
        """Create/reuse the one relationship for this Business and Company."""
        ...

    def update_owned(
        self,
        business_id: UUID,
        prospect_id: UUID,
        expected_version: int,
        prospect: Prospect,
    ) -> Prospect:
        """Reject stale versions instead of overwriting current pursuit state."""
        ...
