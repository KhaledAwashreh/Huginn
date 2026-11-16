"""Immutable command outcome, retained independently from later pursuit state."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True, slots=True)
class SaveRecommendationResponse:
    prospect_id: UUID
    company_id: UUID
    prospect_stage: str
    prospect_version: int
    origin_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    recommendation_status: str

    def snapshot(self) -> JsonSnapshot:
        return JsonSnapshot(
            {
                "prospect_id": str(self.prospect_id),
                "company_id": str(self.company_id),
                "prospect_stage": self.prospect_stage,
                "prospect_version": self.prospect_version,
                "origin_id": str(self.origin_id),
                "recommendation_id": str(self.recommendation_id),
                "assessment_revision_id": str(self.assessment_revision_id),
                "recommendation_status": self.recommendation_status,
            }
        )

    @classmethod
    def from_snapshot(cls, snapshot: JsonSnapshot) -> SaveRecommendationResponse:
        value = snapshot.to_json_object()
        return cls(
            UUID(value["prospect_id"]),
            UUID(value["company_id"]),
            value["prospect_stage"],
            value["prospect_version"],
            UUID(value["origin_id"]),
            UUID(value["recommendation_id"]),
            UUID(value["assessment_revision_id"]),
            value["recommendation_status"],
        )
