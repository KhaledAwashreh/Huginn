from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True)
class GenerateRecommendationsRequest:
    strategy_id: UUID
    limit: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, UUID):
            raise ValidationDomainError("A discovery strategy is required")
        if type(self.limit) is not int or not 1 <= self.limit <= 20:
            raise ValidationDomainError(
                "Recommendation limit must be between one and twenty"
            )
