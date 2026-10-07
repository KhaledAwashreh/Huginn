from uuid import uuid4

import pytest
from pydantic import ValidationError

from huginn.management.presentation.api.primitives import (
    E164Phone,
    Email,
    IanaTimezone,
    NonBlankText,
    PageLimit,
    PageOffset,
    PatchModel,
    StrictModel,
    UUIDValue,
)


class Sample(PatchModel):
    name: NonBlankText | None = None
    count: int | None = None


class PrimitiveSample(StrictModel):
    text: NonBlankText
    email: Email
    phone: E164Phone
    timezone: IanaTimezone
    identifier: UUIDValue
    limit: PageLimit
    offset: PageOffset


def test_shared_primitives_accept_valid_values():
    instance = PrimitiveSample.model_validate_json(
        '{"text":" Hello ","email":"user@example.org",'
        '"phone":"+12025550123","timezone":"Asia/Hebron",'
        f'"identifier":"{uuid4()}","limit":50,"offset":0}}'
    )
    assert instance.text == "Hello"
    assert instance.timezone == "Asia/Hebron"


def test_page_offset_accepts_values_above_one_million():
    values = {
        "text": "x",
        "email": "user@example.org",
        "phone": "+12025550123",
        "timezone": "UTC",
        "identifier": uuid4(),
        "limit": 20,
        "offset": 1_000_001,
    }
    assert PrimitiveSample.model_validate(values).offset == 1_000_001


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "  "),
        ("email", "not-an-email"),
        ("phone", "2025550123"),
        ("timezone", "Mars/Olympus"),
        ("limit", 0),
        ("limit", 101),
        ("offset", -1),
        ("offset", "0"),
    ],
)
def test_shared_primitives_reject_invalid_values(field, value):
    values = {
        "text": "Good",
        "email": "user@example.org",
        "phone": "+12025550123",
        "timezone": "UTC",
        "identifier": str(uuid4()),
        "limit": 20,
        "offset": 0,
    }
    values[field] = value
    with pytest.raises(ValidationError):
        PrimitiveSample.model_validate(values)


def test_strict_models_reject_coercion_and_extra_fields():
    values = {
        "text": "x",
        "email": "user@example.org",
        "phone": "+12025550123",
        "timezone": "UTC",
        "identifier": uuid4(),
        "limit": 20,
        "offset": 0,
    }
    with pytest.raises(ValidationError):
        PrimitiveSample.model_validate({**values, "limit": "20"})
    with pytest.raises(ValidationError):
        PrimitiveSample.model_validate({**values, "extra": True})
    with pytest.raises(ValidationError):
        PrimitiveSample.model_validate({**values, "identifier": str(uuid4())})


def test_patch_tracks_omission_and_explicit_null_separately():
    omitted = Sample.model_validate({})
    explicit_null = Sample.model_validate({"name": None})
    replacement = Sample.model_validate({"count": 0})
    assert omitted.supplied_fields == frozenset()
    assert explicit_null.supplied_fields == frozenset({"name"})
    assert explicit_null.name is None
    assert replacement.supplied_fields == frozenset({"count"})


def test_patch_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Sample.model_validate({"unknown": 1})
