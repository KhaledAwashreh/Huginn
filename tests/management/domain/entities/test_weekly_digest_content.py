"""Frozen email content keeps exact offer membership across replacement."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.weekly_digest_content import WeeklyDigestContent
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.weekly_digest_member import (
    WeeklyDigestMember,
)


def _content():
    member = WeeklyDigestMember(uuid4(), uuid4(), uuid4(), uuid4(), 1)
    return WeeklyDigestContent(
        id=uuid4(),
        delivery_id=uuid4(),
        business_id=uuid4(),
        recipient_user_id=uuid4(),
        version=1,
        created_at=datetime.now(UTC),
        subscription_updated_at=datetime.now(UTC),
        recipient="private@example.test",
        subject="Weekly recommendations",
        body="Private frozen explanation",
        message_id="<content@example.test>",
        members=(member,),
    )


def test_replacement_keeps_original_payload_and_exact_selected_references():
    original = _content()
    replacement = replace(
        original,
        id=uuid4(),
        version=2,
        body="New frozen subset",
        message_id="<replacement@example.test>",
    )
    assert original.body == "Private frozen explanation"
    assert replacement.body == "New frozen subset"
    assert replacement.delivery_id == original.delivery_id
    assert (
        replacement.members[0].assessment_revision_id
        == original.members[0].assessment_revision_id
    )
    assert original.recipient not in repr(original)
    assert original.body not in repr(original)
    with pytest.raises(FrozenInstanceError):
        original.body = "overwritten"


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "duplicate_company",
        "duplicate_cycle",
        "non_contiguous",
        "too_many",
        "mutable",
    ],
)
def test_invalid_frozen_membership_cannot_describe_an_email(kind):
    content = _content()
    first = content.members[0]
    if kind == "empty":
        members = ()
    elif kind == "duplicate_company":
        members = (
            first,
            replace(
                first,
                recommendation_id=uuid4(),
                assessment_revision_id=uuid4(),
                offer_cycle_id=uuid4(),
                position=2,
            ),
        )
    elif kind == "duplicate_cycle":
        members = (
            first,
            replace(
                first,
                company_id=uuid4(),
                recommendation_id=uuid4(),
                assessment_revision_id=uuid4(),
                position=2,
            ),
        )
    elif kind == "non_contiguous":
        members = (replace(first, position=2),)
    elif kind == "too_many":
        members = tuple(
            WeeklyDigestMember(uuid4(), uuid4(), uuid4(), uuid4(), min(index, 7))
            for index in range(1, 9)
        )
    else:
        members = list(content.members)
    with pytest.raises(ValidationDomainError):
        replace(content, members=members)


@pytest.mark.parametrize("field", ["recipient", "subject", "message_id"])
def test_frozen_headers_reject_injection_before_any_transport(field):
    with pytest.raises(ValidationDomainError):
        replace(_content(), **{field: "value\r\nBcc: another@example.test"})
