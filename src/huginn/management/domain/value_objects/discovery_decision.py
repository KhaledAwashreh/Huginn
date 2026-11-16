from dataclasses import dataclass

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.later_pause import LaterPause
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)


@dataclass(frozen=True)
class DiscoveryDecision:
    status: RecommendationStatus
    create_prospect: bool
    prospect_initial_stage: str | None
    add_rejection: bool
    add_pause: bool
    pause: LaterPause | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RecommendationStatus):
            raise ValidationDomainError(
                "Discovery decision status must use its domain value"
            )
        if (
            type(self.create_prospect) is not bool
            or type(self.add_rejection) is not bool
            or type(self.add_pause) is not bool
        ):
            raise ValidationDomainError("Discovery decision flags must be booleans")
        if self.create_prospect != (self.status.value == "converted"):
            raise ValidationDomainError("Only Save converts discovery to prospect")
        if self.add_rejection != (self.status.value == "rejected"):
            raise ValidationDomainError("Only Not relevant rejects discovery")
        if self.create_prospect and self.prospect_initial_stage != "saved":
            raise ValidationDomainError("Saved prospects begin in Saved stage")
        if not self.create_prospect and self.prospect_initial_stage is not None:
            raise ValidationDomainError("Only Save sets an initial prospect stage")
        if self.add_pause != (self.pause is not None):
            raise ValidationDomainError(
                "Later requires its immutable duration snapshot"
            )
