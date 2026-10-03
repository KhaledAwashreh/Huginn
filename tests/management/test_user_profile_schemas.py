from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from huginn.management.requests.professional_profile import (
    ProfessionalCollectionsRequest as ProfessionalCollections,
)
from huginn.management.requests.professional_profile import (
    ProfessionalProfileUpdateRequest as ProfessionalProfilePatch,
)
from huginn.management.requests.user import UserUpdateRequest as UserPatch
from huginn.management.responses.professional_profile import (
    ProfessionalProfileResponse as ProfessionalProfileRead,
)
from huginn.management.responses.user import UserResponse as UserRead


def test_user_and_profile_read_models_expose_safe_public_fields_only():
    assert "password_hash" not in UserRead.model_fields
    assert "password" not in UserRead.model_fields
    assert "account_id" not in UserRead.model_fields
    assert {
        "headline",
        "professional_summary",
        "skills",
        "experience",
        "previous_projects",
    } <= set(ProfessionalProfileRead.model_fields)


def test_user_patch_preserves_required_fields_and_accepts_nullable_timezone():
    patch = UserPatch.model_validate({"timezone": None})
    assert patch.supplied_fields == frozenset({"timezone"})
    assert patch.model_dump(exclude_unset=True) == {"timezone": None}
    assert UserPatch.model_validate({}).supplied_fields == frozenset()
    for field in (
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "country_of_residence",
    ):
        with pytest.raises(ValidationError):
            UserPatch.model_validate({field: None})


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "secret"},
        {"account_id": str(uuid4())},
        {"user_id": str(uuid4())},
        {"unknown": True},
    ],
)
def test_user_patch_rejects_credentials_ownership_and_unknown_fields(payload):
    with pytest.raises(ValidationError):
        UserPatch.model_validate(payload)


def test_profile_patch_tracks_omission_null_and_complete_replacement():
    patch = ProfessionalProfilePatch.model_validate(
        {
            "headline": None,
            "professional_summary": None,
            "skills": [{"name": "Python"}, {"name": "Python"}],
            "previous_projects": [],
        }
    )
    assert patch.supplied_fields == frozenset(
        {"headline", "professional_summary", "skills", "previous_projects"}
    )
    assert patch.experience is None
    assert patch.model_dump(exclude_unset=True, mode="json")["skills"] == [
        {"name": "Python"},
        {"name": "Python"},
    ]
    assert patch.previous_projects == []
    with pytest.raises(ValidationError):
        ProfessionalProfilePatch.model_validate({"skills": None})


@pytest.mark.parametrize(
    "experience",
    [
        {"organization": "Acme", "role": "Engineer", "start_month": "2024-13"},
        {
            "organization": "Acme",
            "role": "Engineer",
            "start_month": "2024-02",
            "end_month": "2024-01",
        },
        {
            "organization": "Acme",
            "role": "Engineer",
            "end_month": "2024-01",
            "is_current": True,
        },
    ],
)
def test_profile_patch_reuses_experience_validation(experience):
    with pytest.raises(ValidationError):
        ProfessionalProfilePatch.model_validate({"experience": [experience]})


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": True},
        {"skills": [{"name": "Python", "years": 4}]},
        {"experience": [{"organization": "Acme", "role": "Engineer", "current": True}]},
        {"previous_projects": "project"},
        {"skills": [{"name": 7}]},
    ],
)
def test_profile_patch_rejects_extra_fields_and_coercion(payload):
    from huginn.management.requests.professional_profile import (
        ProfessionalProfileUpdateRequest as ProfessionalProfilePatch,
    )

    with pytest.raises(ValidationError):
        ProfessionalProfilePatch.model_validate(payload)


def test_profile_read_uses_established_collection_models():
    collections = ProfessionalCollections.model_validate(
        {"skills": [{"name": "Python"}]}
    )
    read = ProfessionalProfileRead.model_validate(
        {
            "id": uuid4(),
            "user_id": uuid4(),
            **collections.model_dump(),
            "headline": None,
            "professional_summary": None,
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2025, 1, 1, tzinfo=UTC),
        }
    )
    assert read.skills[0].name == "Python"
