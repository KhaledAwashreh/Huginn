"""Authenticated owner match page input."""

from dataclasses import dataclass

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.match_status import MatchStatus


@dataclass(frozen=True, slots=True)
class ListMatchesRequest:
    principal: Principal
    status: MatchStatus | None = None
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        _validate_page(self.limit, self.offset)


def _validate_page(limit: int, offset: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValidationDomainError("limit must be between 1 and 100")
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or not 0 <= offset <= 9_223_372_036_854_775_807
    ):
        raise ValidationDomainError("offset must be a nonnegative PostgreSQL bigint")
