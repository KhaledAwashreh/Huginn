"""Authenticated signal page input requiring an owned match ID."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True, slots=True)
class ListMatchSignalsRequest:
    principal: Principal
    match_id: UUID
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or not 1 <= self.limit <= 100
        ):
            raise ValidationDomainError("limit must be between 1 and 100")
        if (
            isinstance(self.offset, bool)
            or not isinstance(self.offset, int)
            or not 0 <= self.offset <= 9_223_372_036_854_775_807
        ):
            raise ValidationDomainError(
                "offset must be a nonnegative PostgreSQL bigint"
            )
