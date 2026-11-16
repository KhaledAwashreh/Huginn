from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.suppression_block import SuppressionBlock


class SuppressionBlockRepository(Protocol):
    def list_active(
        self, business_id: UUID, company_id: UUID, at: datetime
    ) -> tuple[SuppressionBlock, ...]: ...
    def list_history(
        self, business_id: UUID, company_id: UUID
    ) -> tuple[SuppressionBlock, ...]: ...
    def get_owned(
        self, business_id: UUID, block_id: UUID
    ) -> SuppressionBlock | None: ...
    def append(self, block: SuppressionBlock) -> SuppressionBlock: ...
    def clear_one(
        self,
        business_id: UUID,
        company_id: UUID,
        block_id: UUID,
        expected_version: int,
        actor_user_id: UUID,
        cleared_at: datetime,
    ) -> SuppressionBlock:
        """Clear only this versioned block and retain its clear time/actor."""
        ...
