"""Owned match projection joined to current Gold company context."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.domain.value_objects.match_status import MatchStatus


@dataclass(frozen=True, slots=True)
class UserMatch:
    id: UUID
    user_id: UUID
    status: MatchStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    company: CurrentCompany
