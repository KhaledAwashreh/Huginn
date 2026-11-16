from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.domain.entities.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedback,
)
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)


def test_feedback_attribution_binds_exact_revision_and_actor_without_workflow_side_effects():
    record = RecommendationAssessmentFeedback(
        id=uuid4(),
        business_id=uuid4(),
        recommendation_id=uuid4(),
        assessment_revision_id=uuid4(),
        actor_user_id=uuid4(),
        recorded_at=datetime(2027, 1, 1, tzinfo=UTC),
        feedback=RecommendationFeedback(usefulness="useful"),
    )
    assert record.assessment_revision_id
    assert record.actor_user_id
    assert record.feedback.usefulness == "useful"
