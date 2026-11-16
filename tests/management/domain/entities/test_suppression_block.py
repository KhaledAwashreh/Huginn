from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind


def test_expiring_block_and_rejection_are_independent_immutable_records():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    pause = SuppressionBlock(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        kind=SuppressionKind("pause"),
        created_at=now,
        created_by_user_id=uuid4(),
        expires_at=now + timedelta(days=7),
    )
    rejection = SuppressionBlock(
        id=uuid4(),
        business_id=pause.business_id,
        company_id=pause.company_id,
        kind=SuppressionKind("rejection"),
        created_at=now,
        created_by_user_id=uuid4(),
    )
    cleared_pause = replace(pause, cleared_at=now, cleared_by_user_id=uuid4())
    assert not cleared_pause.is_active_at(now)
    assert rejection.is_active_at(now)
    assert rejection.is_active_at(now + timedelta(days=100))
    assert pause.is_active_at(now + timedelta(days=6))


def test_delivery_states_are_not_generic_suppression_kinds():
    for kind in ("pending_delivery", "uncertain_delivery"):
        try:
            SuppressionKind(kind)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{kind} must come from OfferCycle state")


def test_rejection_cannot_expire_and_cooldown_requires_a_finite_expiry():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    common = {
        "id": uuid4(),
        "business_id": uuid4(),
        "company_id": uuid4(),
        "created_at": now,
    }
    with pytest.raises(ValidationDomainError):
        SuppressionBlock(
            **common,
            kind=SuppressionKind("rejection"),
            created_by_user_id=uuid4(),
            expires_at=now + timedelta(days=10),
        )
    with pytest.raises(ValidationDomainError):
        SuppressionBlock(**common, kind=SuppressionKind("cooldown"))


def test_expiry_uses_actual_effective_time_not_later_recording_time():
    effective = datetime(2027, 1, 1, tzinfo=UTC)
    recorded = effective + timedelta(days=35)
    expiry = effective + timedelta(days=30)
    block = SuppressionBlock(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        kind=SuppressionKind("cooldown"),
        created_at=recorded,
        effective_at=effective,
        expires_at=expiry,
    )
    assert block.is_active_at(effective + timedelta(days=29))
    assert not block.is_active_at(expiry)
    assert not block.is_active_at(recorded)
