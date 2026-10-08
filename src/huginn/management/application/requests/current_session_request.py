"""Authenticated server input for session bootstrap."""

from dataclasses import dataclass, field
from uuid import UUID

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True, slots=True)
class CurrentSessionRequest:
    principal: Principal
    session_id: UUID
    raw_token: str = field(repr=False)
