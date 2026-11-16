from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)


@dataclass(frozen=True)
class AssessmentRevision:
    id: UUID
    recommendation_id: UUID
    business_id: UUID
    company_id: UUID
    revision_number: int
    assessed_at: datetime
    strategy_assessments: tuple[StrategyAssessmentSnapshot, ...]
    professional_profile_snapshot: JsonSnapshot
    evidence_snapshots: tuple[JsonSnapshot, ...]
    evidence_observation_ids: tuple[UUID, ...]
    policy_versions: tuple[str, ...]
    evaluation_seed: str | None = None
    assessed_by_user_id: UUID | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (
                self.id,
                self.recommendation_id,
                self.business_id,
                self.company_id,
            )
        ):
            raise ValidationDomainError("Revision identities must be UUIDs")
        if self.assessed_by_user_id is not None and not isinstance(
            self.assessed_by_user_id, UUID
        ):
            raise ValidationDomainError("Assessment actor must be a User UUID")
        if type(self.revision_number) is not int or self.revision_number < 1:
            raise ValidationDomainError("Revision number must be positive")
        _aware(self.assessed_at)
        if (
            type(self.strategy_assessments) is not tuple
            or not self.strategy_assessments
        ):
            raise ValidationDomainError("At least one strategy assessment is required")
        if any(
            not isinstance(value, StrategyAssessmentSnapshot)
            for value in self.strategy_assessments
        ):
            raise ValidationDomainError(
                "Strategy assessments must be immutable snapshots"
            )
        if len({item.strategy_id for item in self.strategy_assessments}) != len(
            self.strategy_assessments
        ):
            raise ValidationDomainError(
                "A revision cannot repeat a strategy association"
            )
        if not isinstance(self.professional_profile_snapshot, JsonSnapshot):
            object.__setattr__(
                self,
                "professional_profile_snapshot",
                JsonSnapshot(self.professional_profile_snapshot),
            )
        if type(self.evidence_snapshots) is not tuple:
            raise ValidationDomainError("Evidence snapshots must be a tuple")
        object.__setattr__(
            self,
            "evidence_snapshots",
            tuple(
                value if isinstance(value, JsonSnapshot) else JsonSnapshot(value)
                for value in self.evidence_snapshots
            ),
        )
        if type(self.evidence_observation_ids) is not tuple or any(
            not isinstance(value, UUID) for value in self.evidence_observation_ids
        ):
            raise ValidationDomainError(
                "Evidence observation identifiers must be UUIDs"
            )
        if len(set(self.evidence_observation_ids)) != len(
            self.evidence_observation_ids
        ):
            raise ValidationDomainError(
                "Evidence observation identifiers must be unique"
            )
        if (
            type(self.policy_versions) is not tuple
            or not self.policy_versions
            or any(
                not isinstance(value, str) or not value.strip()
                for value in self.policy_versions
            )
        ):
            raise ValidationDomainError(
                "Policy versions must be a nonempty tuple of names"
            )


def _aware(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError("Assessment time must include a timezone")
