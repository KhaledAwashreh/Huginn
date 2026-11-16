from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage


def test_prospect_starts_as_manual_saved_relationship_with_optimistic_version():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    prospect = Prospect(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        stage=ProspectStage("saved"),
        created_at=now,
        updated_at=now,
    )
    assert prospect.stage.value == "saved"
    assert prospect.version == 1
    assert prospect.last_active_stage is None


def test_closed_prospect_retains_last_active_stage_for_explicit_reopen():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    closed = Prospect(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        stage=ProspectStage("closed"),
        created_at=now,
        updated_at=now,
        last_active_stage=ProspectStage("in_conversation"),
    )
    assert closed.last_active_stage.value == "in_conversation"
    with pytest.raises(ValidationDomainError):
        Prospect(
            id=uuid4(),
            business_id=uuid4(),
            company_id=uuid4(),
            stage=ProspectStage("closed"),
            created_at=now,
            updated_at=now,
        )
