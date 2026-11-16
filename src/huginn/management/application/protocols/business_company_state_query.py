"""Read-only current selection facts shared by generation and presentation."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)


class BusinessCompanyStateQuery(Protocol):
    def company_states(
        self, business_id: UUID, company_ids: tuple[UUID, ...], as_of: datetime
    ) -> tuple[BusinessCompanyState, ...]:
        """Return facts in input order without locks, expiry release or other writes."""
        ...
