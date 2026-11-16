"""Shared literal search and bounded pagination for prospecting reads."""

from dataclasses import dataclass

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class ListProspectingRequest:
    search: str = ""
    offset: int = 0
    limit: int = 20

    def __post_init__(self) -> None:
        if type(self.search) is not str or len(self.search) > 200:
            raise ValidationDomainError("search must contain at most 200 characters")
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValidationDomainError("limit must be between 1 and 100")
        if (
            type(self.offset) is not int
            or not 0 <= self.offset <= 9_223_372_036_854_775_807
        ):
            raise ValidationDomainError(
                "offset must be a nonnegative PostgreSQL bigint"
            )
        object.__setattr__(self, "search", self.search.strip())
