from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.entities.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedback,
)
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from huginn.management.persistence.repositories.recommendation import (
    PostgresRecommendationRepository,
)
from huginn.management.persistence.repositories.recommendation_assessment_feedback import (
    PostgresRecommendationAssessmentFeedbackRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_assessment_revision,
    valid_recommendation,
)


def test_feedback_roundtrips_as_immutable_revision_attributed_history(
    management_database_url,
):
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendation = PostgresRecommendationRepository(session).create_open(
            valid_recommendation(identity, at=now)
        )
        revisions = PostgresAssessmentRevisionRepository(session)
        old_revision = revisions.append(
            valid_assessment_revision(identity, recommendation, at=now)
        )
        revision = revisions.append(
            valid_assessment_revision(
                identity, recommendation, revision_number=2, at=now
            )
        )
        repository = PostgresRecommendationAssessmentFeedbackRepository(session)
        feedback = RecommendationAssessmentFeedback(
            id=uuid4(),
            business_id=identity.business_id,
            recommendation_id=recommendation.id,
            assessment_revision_id=revision.id,
            actor_user_id=identity.owner_user_id,
            recorded_at=now,
            feedback=RecommendationFeedback(
                usefulness="not_useful",
                reasons=("timing", "evidence_wrong"),
                correction="The hiring signal is old.",
                next_step="skip",
                outcome="not_contacted",
                notes="Keep linked to the revision that was shown.",
            ),
        )

        assert repository.append(feedback) == feedback
        with pytest.raises(ConflictError), connection.transaction():
            repository.append(feedback)
        assert repository.list_for_revision(
            identity.business_id, recommendation.id, revision.id
        ) == (feedback,)
        assert (
            repository.list_for_revision(
                identity.business_id, recommendation.id, old_revision.id
            )
            == ()
        )
        assert (
            repository.list_for_revision(uuid4(), recommendation.id, revision.id) == ()
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM operational.recommendation_assessment_feedback "
                "WHERE recommendation_id=%s",
                (recommendation.id,),
            ).fetchone()[0]
            == 1
        )
        persisted = connection.execute(
            "SELECT business_id,recommendation_id,assessment_revision_id,"
            "actor_user_id,recorded_at,payload FROM "
            "operational.recommendation_assessment_feedback WHERE id=%s",
            (feedback.id,),
        ).fetchone()
        assert persisted == (
            identity.business_id,
            recommendation.id,
            revision.id,
            identity.owner_user_id,
            now,
            {
                "usefulness": "not_useful",
                "reasons": ["timing", "evidence_wrong"],
                "correction": "The hiring signal is old.",
                "next_step": "skip",
                "outcome": "not_contacted",
                "notes": "Keep linked to the revision that was shown.",
            },
        )
