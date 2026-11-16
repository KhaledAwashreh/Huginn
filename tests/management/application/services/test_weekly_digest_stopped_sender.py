from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.services.recover_weekly_digest_service import (
    RecoverWeeklyDigestService,
)
from huginn.management.domain.entities.weekly_digest_delivery import (
    WeeklyDigestDelivery,
)
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.common import Principal


def test_stopped_sender_requires_exact_fences_and_replays_without_reapplying():
    now = datetime(2026, 11, 16, tzinfo=UTC)
    principal = Principal(uuid4(), uuid4())
    business_id, content_id, company_id, cycle_id, recommendation_id, revision_id = (
        uuid4() for _ in range(6)
    )
    delivery = WeeklyDigestDelivery(
        uuid4(),
        business_id,
        principal.user_id,
        date(2026, 11, 16),
        now,
        "sending",
        3,
        content_id,
        now,
    )
    member = SimpleNamespace(
        company_id=company_id,
        offer_cycle_id=cycle_id,
        recommendation_id=recommendation_id,
        assessment_revision_id=revision_id,
    )
    content = SimpleNamespace(id=content_id, members=(member,))
    cycle = SimpleNamespace(
        status=SimpleNamespace(value="sending"),
        recommendation_id=recommendation_id,
        selected_revision_id=revision_id,
        claim_token="token",
        sending_started_at=now,
    )
    events, transitions = [], []

    class Repository:
        def get_for_update(self, *args):
            return delivery

        def list_events(self, *args):
            return tuple(events)

        def reconcile_stopped_sending(self, *args, **kwargs):
            nonlocal delivery
            transitions.append("delivery")
            events.append(
                SimpleNamespace(
                    event_kind="unknown",
                    actor_user_id=principal.user_id,
                    reason=args[6],
                    payload=args[8],
                )
            )
            delivery = replace(delivery, state="unknown", version=4, settled_at=now)
            return delivery

    class Work:
        businesses = SimpleNamespace(
            get_by_owner_user_id=lambda user_id: SimpleNamespace(id=business_id)
        )
        offer_cycles = SimpleNamespace(
            get_owned=lambda *args: cycle,
            accepted_cadence=lambda *args: SimpleNamespace(accepted_at=now),
            settle_sending=lambda *args, **kwargs: transitions.append("cycle"),
        )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def commit(self):
            pass

        def lock_business_company(self, *args):
            pass

    service = RecoverWeeklyDigestService(
        Work,
        delivery_repository_factory=lambda work: Repository(),
        content_repository_factory=lambda work: SimpleNamespace(
            get_current=lambda *args: content
        ),
        clock=lambda: now,
    )
    request = SimpleNamespace(
        delivery_id=delivery.id,
        expected_version=3,
        expected_content_id=content_id,
        expected_sending_started_at=now,
        expected_offer_cycle_ids=(cycle_id,),
        sender_stopped=True,
        reason="Original sender stopped and verified",
    )

    for field, value in (
        ("expected_version", 2),
        ("expected_content_id", uuid4()),
        ("expected_offer_cycle_ids", (uuid4(),)),
        ("sender_stopped", False),
    ):
        with pytest.raises((ConflictError, ValueError)):
            service.reconcile_stopped_sender(
                principal, SimpleNamespace(**{**vars(request), field: value})
            )
        assert transitions == []
    for field, value in (
        ("status", SimpleNamespace(value="unknown")),
        ("selected_revision_id", uuid4()),
        ("claim_token", None),
    ):
        original = getattr(cycle, field)
        setattr(cycle, field, value)
        with pytest.raises(ConflictError):
            service.reconcile_stopped_sender(principal, request)
        setattr(cycle, field, original)
        assert transitions == []
    assert service.reconcile_stopped_sender(principal, request).state == "unknown"
    assert transitions == ["cycle", "delivery"]
    assert service.reconcile_stopped_sender(principal, request).state == "unknown"
    assert transitions == ["cycle", "delivery"]
    with pytest.raises(ConflictError):
        service.reconcile_stopped_sender(
            principal, SimpleNamespace(**{**vars(request), "reason": "different"})
        )
    delivery = replace(delivery, state="sent", version=5, accepted_at=now)
    assert service.reconcile_stopped_sender(principal, request).state == "sent"
    assert transitions == ["cycle", "delivery"]
