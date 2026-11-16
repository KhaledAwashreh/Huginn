"""Delivery audit events retain attributed recovery and actual handoff time."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.management.domain.entities.weekly_digest_delivery_event import (
    WeeklyDigestDeliveryEvent,
)
from huginn.management.domain.errors.errors import ValidationDomainError


def test_recovery_retains_actual_handoff_and_later_attributed_observation():
    accepted = datetime(2026, 11, 14, 12, tzinfo=UTC)
    observed = accepted + timedelta(days=35)
    event = WeeklyDigestDeliveryEvent(
        id=uuid4(),
        delivery_id=uuid4(),
        business_id=uuid4(),
        delivery_version=4,
        event_kind="unknown_resolved",
        recorded_at=observed,
        content_id=uuid4(),
        actor_user_id=uuid4(),
        reason="Confirmed accepted handoff from delivery evidence",
        outcome="sent",
        accepted_at=accepted,
    )
    assert event.accepted_at == accepted
    assert event.recorded_at == observed


@pytest.mark.parametrize("missing", ["actor", "reason", "acceptance", "outcome"])
def test_unknown_recovery_requires_explicit_attribution_and_truthful_outcome(missing):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "delivery_id": uuid4(),
        "business_id": uuid4(),
        "delivery_version": 4,
        "event_kind": "unknown_resolved",
        "recorded_at": now,
        "content_id": uuid4(),
        "actor_user_id": uuid4(),
        "reason": "Confirmed actual outcome",
        "outcome": "sent",
        "accepted_at": now,
    }
    values[
        {
            "actor": "actor_user_id",
            "reason": "reason",
            "acceptance": "accepted_at",
            "outcome": "outcome",
        }[missing]
    ] = None
    with pytest.raises(ValidationDomainError):
        WeeklyDigestDeliveryEvent(**values)
