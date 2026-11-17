from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService

NOW = datetime(2026, 11, 15, tzinfo=UTC)


class Work:
    connection = object()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def commit(self):
        pass


class SubscriptionAccess:
    def __init__(self):
        self.subscription = DigestSubscription(
            uuid4(), uuid4(), "verified@example.test", NOW
        )

    def list_eligible(self, limit):
        return (self.subscription,)


class Source:
    def active_profiles(self, owner_user_id):
        return (
            SimpleNamespace(
                snapshot_json='{"offering": {}, "icp": {}}', offering_text=""
            ),
        )


class DeliveryRepository:
    def __init__(self):
        self.reservations = 0

    def reserve(self, *args):
        self.reservations += 1
        raise AssertionError("Invalid strategy must not reserve a delivery")


class Sender:
    def send(self, message):
        raise AssertionError("Invalid strategy must not send")


def _service(*, dry_run=False):
    access = SubscriptionAccess()
    delivery = DeliveryRepository()
    service = WeeklyDigestService(
        lambda: Work(),
        subscription_access_factory=lambda _work: access,
        delivery_repository_factory=lambda _work: delivery,
        content_repository_factory=lambda _work: None,
        source_factory=lambda _connection: Source(),
        generation=object(),
        renderer=object(),
        sender=Sender(),
        sender_address="weekly@example.test",
        clock=lambda: NOW,
    )
    return service, delivery


def test_dry_run_reads_subscriptions_without_validating_or_reserving():
    service, delivery = _service(dry_run=True)
    result = service.run(dry_run=True)
    assert result["eligible"] == 1
    assert result["sent"] == result["failed"] == 0
    assert delivery.reservations == 0


def test_invalid_active_profile_does_not_consume_weekly_reservation():
    service, delivery = _service()
    result = service.run()
    assert result["skipped"] == 1
    assert delivery.reservations == 0


@pytest.mark.parametrize("error_type", [RuntimeError, TypeError])
def test_unexpected_profile_validation_failure_is_logged_without_reserving(
    error_type, monkeypatch, caplog
):
    def fail_validation(profile):
        raise error_type("Unexpected projection failure")

    monkeypatch.setattr(
        "huginn.management.application.services.weekly_digest.validated_profile_inputs",
        fail_validation,
    )
    service, delivery = _service()
    result = service.run()
    assert result["failed"] == 1
    assert result["skipped"] == 0
    assert delivery.reservations == 0
    assert "Weekly digest processing failed" in caplog.text


@pytest.mark.parametrize("count", [0, 2])
def test_simple_discovery_ambiguous_profile_skips_before_reservation(
    count, monkeypatch
):
    service, delivery = _service()
    service._simple_discovery_enabled = True
    monkeypatch.setattr(
        Source, "active_profiles", lambda self, owner: (object(),) * count
    )
    monkeypatch.setattr(
        "huginn.management.application.services.weekly_digest.validated_profile_inputs",
        lambda profile: (),
    )
    result = service.run()
    assert result["skipped"] == 1
    assert delivery.reservations == 0
