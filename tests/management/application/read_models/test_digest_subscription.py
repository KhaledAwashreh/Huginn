from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)


def test_digest_subscription_has_required_business_identity_and_utc_version():
    updated_at = datetime(2048, 8, 9, 10, tzinfo=timezone(timedelta(hours=3)))
    value = DigestSubscription(uuid4(), uuid4(), "private@example.test", updated_at)

    assert value.updated_at == datetime(2048, 8, 9, 7, tzinfo=UTC)
    assert value.version == "2048-08-09T07:00:00+00:00"
    assert "private@example.test" not in repr(value)


@pytest.mark.parametrize(
    "arguments",
    (
        ("not-a-business-id", uuid4(), "person@example.test", datetime.now(UTC)),
        (uuid4(), uuid4(), "", datetime.now(UTC)),
        (uuid4(), uuid4(), "person@example.test", datetime(2048, 8, 9)),
    ),
)
def test_digest_subscription_rejects_incomplete_identity_recipient_or_time(arguments):
    with pytest.raises(ValueError):
        DigestSubscription(*arguments)


def test_business_identity_and_timestamp_are_required_constructor_arguments():
    with pytest.raises(TypeError):
        DigestSubscription(uuid4(), "person@example.test")
