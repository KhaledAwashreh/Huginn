from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from huginn.management.schemas import OfferingCreate, OfferingPatch, OfferingRead


def test_offering_models_validate_nonblank_values_and_track_patch_presence():
    create = OfferingCreate.model_validate(
        {"name": " Consulting ", "description": " Audit "}
    )
    assert (create.name, create.description) == ("Consulting", "Audit")
    patch = OfferingPatch.model_validate({"description": "Review"})
    assert patch.supplied_fields == frozenset({"description"})
    assert patch.model_dump(exclude_unset=True) == {"description": "Review"}
    assert OfferingPatch.model_validate({}).supplied_fields == frozenset()


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "description": "Valid"},
        {"name": "Valid", "description": "\t"},
        {"name": "Valid", "description": "Valid", "user_id": str(uuid4())},
        {"name": "Valid", "description": "Valid", "id": str(uuid4())},
        {"name": "Valid", "description": "Valid", "created_at": "2025-01-01T00:00:00Z"},
        {"name": 7, "description": "Valid"},
    ],
)
def test_offering_create_rejects_blank_unknown_or_coerced_values(payload):
    with pytest.raises(ValidationError):
        OfferingCreate.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": None},
        {"description": "  "},
        {"user_id": str(uuid4())},
        {"id": str(uuid4())},
        {"updated_at": "2025-01-01T00:00:00Z"},
        {"unknown": 1},
    ],
)
def test_offering_patch_rejects_nonwritable_and_invalid_values(payload):
    with pytest.raises(ValidationError):
        OfferingPatch.model_validate(payload)


def test_offering_read_model_exposes_owner_and_timestamps():
    now = datetime(2025, 1, 1, tzinfo=UTC)
    model = OfferingRead.model_validate(
        {
            "id": uuid4(),
            "user_id": uuid4(),
            "name": "Consulting",
            "description": "Audit",
            "created_at": now,
            "updated_at": now,
        }
    )
    assert model.name == "Consulting"
