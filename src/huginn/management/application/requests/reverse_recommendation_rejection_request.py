"""Intent to reverse one Business-owned rejection block."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class ReverseRecommendationRejectionRequest:
    suppression_block_id: UUID
    expected_version: int
    request_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.suppression_block_id, UUID):
            raise ValidationDomainError("Suppression block ID must be a UUID")
        if type(self.expected_version) is not int or self.expected_version < 1:
            raise ValidationDomainError("Expected suppression version must be positive")
        if type(self.request_key) is not str or not self.request_key.strip():
            raise ValidationDomainError("Request key is required")
