from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.management.domain.entities.offer_cycle import OfferCycle
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus


def test_preparing_claim_has_finite_lease_and_bound_revision():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    cycle = OfferCycle(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        recommendation_id=uuid4(),
        selected_revision_id=uuid4(),
        idempotency_key="request-1",
        payload_fingerprint="a" * 64,
        status=OfferCycleStatus("preparing"),
        claim_token="opaque-token",
        lease_expires_at=now + timedelta(minutes=5),
        created_at=now,
        updated_at=now,
    )
    assert cycle.selected_revision_id
    assert cycle.lease_expires_at == now + timedelta(minutes=5)
    assert cycle.presented_at is None


@pytest.mark.parametrize(
    "changes",
    [
        {"status": OfferCycleStatus("preparing"), "claim_token": None},
        {"status": OfferCycleStatus("preparing"), "lease_expires_at": None},
        {
            "status": OfferCycleStatus("sending"),
            "lease_expires_at": datetime(2027, 1, 1, tzinfo=UTC),
            "sending_started_at": datetime(2027, 1, 1, tzinfo=UTC),
        },
        {
            "status": OfferCycleStatus("unknown"),
            "lease_expires_at": datetime(2027, 1, 1, tzinfo=UTC),
            "sending_started_at": datetime(2027, 1, 1, tzinfo=UTC),
        },
    ],
)
def test_preparing_needs_token_and_lease_but_sending_unknown_never_have_a_lease(
    changes,
):
    now = datetime(2027, 1, 1, tzinfo=UTC)
    values = {
        "id": uuid4(),
        "business_id": uuid4(),
        "company_id": uuid4(),
        "recommendation_id": uuid4(),
        "selected_revision_id": uuid4(),
        "idempotency_key": "request-1",
        "payload_fingerprint": "a" * 64,
        "status": OfferCycleStatus("preparing"),
        "claim_token": "token",
        "lease_expires_at": now + timedelta(minutes=5),
        "created_at": now,
        "updated_at": now,
    }
    values.update(changes)
    with pytest.raises(ValidationDomainError):
        OfferCycle(**values)


def test_only_confirmed_cycle_records_presentation_time():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    values = {
        "id": uuid4(),
        "business_id": uuid4(),
        "company_id": uuid4(),
        "recommendation_id": uuid4(),
        "selected_revision_id": uuid4(),
        "idempotency_key": "request-1",
        "payload_fingerprint": "a" * 64,
        "status": OfferCycleStatus("sending"),
        "claim_token": "token",
        "lease_expires_at": None,
        "sending_started_at": now,
        "created_at": now,
        "updated_at": now,
        "presented_at": now,
    }
    with pytest.raises(ValidationDomainError):
        OfferCycle(**values)
