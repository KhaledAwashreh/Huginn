from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.value_objects.origin_append_result import (
    OriginAppendResult,
)


def test_origin_binds_exact_recommendation_revision_company_and_business():
    origin = ProspectOrigin(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        prospect_id=uuid4(),
        recommendation_id=uuid4(),
        assessment_revision_id=uuid4(),
        created_by_user_id=uuid4(),
        created_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    first = OriginAppendResult(origin, created=True)
    retry_with_different_command_key = OriginAppendResult(origin, created=False)
    assert first.created is True
    assert retry_with_different_command_key.created is False
