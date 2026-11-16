"""One reservation retains authorization, acceptance and recovery chronology."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.management.domain.entities.weekly_digest_delivery import (
    WeeklyDigestDelivery,
)
from huginn.management.domain.errors.errors import ValidationDomainError


def _reservation():
    return WeeklyDigestDelivery(
        uuid4(),
        uuid4(),
        uuid4(),
        date(2026, 11, 9),
        datetime(2026, 11, 14, 12, tzinfo=UTC),
    )


def test_authorization_actual_acceptance_and_late_recovery_are_distinct():
    original = _reservation()
    authorized = original.created_at + timedelta(minutes=1)
    accepted = authorized + timedelta(seconds=10)
    recovered = accepted + timedelta(days=35)
    sending = replace(
        original,
        state="sending",
        version=2,
        current_content_id=uuid4(),
        sending_started_at=authorized,
    )
    unknown = replace(
        sending,
        state="unknown",
        version=3,
        settled_at=authorized + timedelta(minutes=1),
    )
    confirmed = replace(
        unknown, state="sent", version=4, settled_at=recovered, accepted_at=accepted
    )
    assert original.state == "preparing"
    assert unknown.accepted_at is None
    assert confirmed.accepted_at == accepted
    assert confirmed.settled_at == recovered
    assert confirmed.sending_started_at == authorized


@pytest.mark.parametrize(
    "fields",
    [
        {"state": "sending"},
        {"state": "sent"},
        {"state": "unknown"},
        {"state": "preparing", "accepted_at": datetime(2026, 11, 14, 12, tzinfo=UTC)},
        {"week_start": date(2026, 11, 10)},
        {"version": True},
        {"created_at": datetime(2026, 11, 14)},
    ],
)
def test_impossible_reservation_state_is_rejected(fields):
    with pytest.raises(ValidationDomainError):
        replace(_reservation(), **fields)
