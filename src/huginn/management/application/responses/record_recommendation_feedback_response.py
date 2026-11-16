"""Immutable result of recording recommendation feedback."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.entities.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedback,
)
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)


@dataclass(frozen=True, slots=True)
class RecordRecommendationFeedbackResponse:
    feedback: RecommendationAssessmentFeedback

    def snapshot(self) -> JsonSnapshot:
        entry = self.feedback
        value = entry.feedback
        return JsonSnapshot(
            {
                "id": str(entry.id),
                "business_id": str(entry.business_id),
                "recommendation_id": str(entry.recommendation_id),
                "assessment_revision_id": str(entry.assessment_revision_id),
                "actor_user_id": str(entry.actor_user_id),
                "recorded_at": entry.recorded_at.isoformat(),
                "feedback": {
                    "usefulness": value.usefulness,
                    "reasons": list(value.reasons),
                    "correction": value.correction,
                    "next_step": value.next_step,
                    "outcome": value.outcome,
                    "notes": value.notes,
                },
            }
        )

    @classmethod
    def from_snapshot(
        cls, snapshot: JsonSnapshot
    ) -> RecordRecommendationFeedbackResponse:
        value = snapshot.to_json_object()
        feedback = value["feedback"]
        return cls(
            RecommendationAssessmentFeedback(
                UUID(value["id"]),
                UUID(value["business_id"]),
                UUID(value["recommendation_id"]),
                UUID(value["assessment_revision_id"]),
                UUID(value["actor_user_id"]),
                datetime.fromisoformat(value["recorded_at"]),
                RecommendationFeedback(
                    feedback["usefulness"],
                    tuple(feedback["reasons"]),
                    feedback["correction"],
                    feedback["next_step"],
                    feedback["outcome"],
                    feedback["notes"],
                ),
            )
        )
