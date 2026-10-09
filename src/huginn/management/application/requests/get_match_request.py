"""Authenticated owned match detail input."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True, slots=True)
class GetMatchRequest:
    principal: Principal
    match_id: UUID
