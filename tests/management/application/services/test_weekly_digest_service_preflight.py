from datetime import UTC, datetime
from uuid import uuid4

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
        return (object(),)


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
