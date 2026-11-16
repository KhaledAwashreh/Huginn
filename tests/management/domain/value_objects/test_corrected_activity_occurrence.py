from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.corrected_activity_occurrence import (
    CorrectedActivityOccurrence,
)


def test_correction_head_and_sequence_must_be_consistent():
    with pytest.raises(ValidationDomainError):
        CorrectedActivityOccurrence(
            uuid4(), datetime(2026, 11, 14, tzinfo=UTC), None, 1
        )
