"""PostgreSQL adapter for immutable feedback on shown assessment revisions."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedback,
)
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.management.persistence.contracts.repositories.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedbackRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresRecommendationAssessmentFeedbackRepository(
    RecommendationAssessmentFeedbackRepository
):
    _columns = (
        "id,business_id,recommendation_id,assessment_revision_id,actor_user_id,"
        "recorded_at,payload"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> RecommendationAssessmentFeedback:
        payload = row[6]
        feedback = RecommendationFeedback(
            usefulness=payload["usefulness"],
            reasons=tuple(payload.get("reasons", ())),
            correction=payload.get("correction", ""),
            next_step=payload.get("next_step", "none"),
            outcome=payload.get("outcome", "unknown"),
            notes=payload.get("notes", ""),
        )
        return RecommendationAssessmentFeedback(
            id=row[0],
            business_id=row[1],
            recommendation_id=row[2],
            assessment_revision_id=row[3],
            actor_user_id=row[4],
            recorded_at=row[5],
            feedback=feedback,
        )

    def list_for_revision(
        self, business_id: UUID, recommendation_id: UUID, revision_id: UUID
    ) -> tuple[RecommendationAssessmentFeedback, ...]:
        rows = self.connection.execute(
            f"SELECT {self._columns} "
            "FROM operational.recommendation_assessment_feedback "
            "WHERE business_id=%s AND recommendation_id=%s "
            "AND assessment_revision_id=%s ORDER BY recorded_at,id",
            (business_id, recommendation_id, revision_id),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def append(
        self, feedback: RecommendationAssessmentFeedback
    ) -> RecommendationAssessmentFeedback:
        payload = {
            "usefulness": feedback.feedback.usefulness,
            "reasons": list(feedback.feedback.reasons),
            "correction": feedback.feedback.correction,
            "next_step": feedback.feedback.next_step,
            "outcome": feedback.feedback.outcome,
            "notes": feedback.feedback.notes,
        }
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.recommendation_assessment_feedback ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                f"RETURNING {self._columns}",
                (
                    feedback.id,
                    feedback.business_id,
                    feedback.recommendation_id,
                    feedback.assessment_revision_id,
                    feedback.actor_user_id,
                    feedback.recorded_at,
                    JsonParameter(payload),
                ),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23505":
                raise ConflictError("Recommendation feedback already exists") from exc
            raise ValidationDomainError(
                "Recommendation feedback violates a persistence constraint"
            ) from exc
        assert row is not None
        return self._map(row)
