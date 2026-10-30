from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService

NOW = datetime(2026, 10, 28, tzinfo=UTC)


class Work:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def commit(self):
        pass


class Store:
    def __init__(self):
        self.subscription = DigestSubscription(
            uuid4(), "verified@example.test", NOW.isoformat()
        )
        self.company = uuid4()
        self.claimed = False
        self.prepared = []
        self.states = []

    def subscriptions(self, limit):
        return (self.subscription,)

    def eligible(self, subscription):
        return True

    def reserve(self, *args):
        if self.claimed:
            return None
        self.claimed = True
        return uuid4()

    def previous_companies(self, user):
        return frozenset((self.company,))

    def prepare(self, *args):
        self.prepared.append(args)

    def settle(self, id, state, now):
        self.states.append(state)


class Recommendations:
    def __init__(self):
        self.calls = []
        self.empty = False

    def weekly_profiles(self, user):
        return () if getattr(self, "invalid", False) else ("valid snapshot",)

    def generate_weekly(self, user, *, exclude_company_ids=frozenset(), profiles=None):
        assert profiles == ("valid snapshot",)
        self.calls.append((user, exclude_company_ids))
        return {
            "id": str(uuid4()),
            "items": []
            if self.empty
            else [
                {
                    "id": "a" * 64,
                    "company": {
                        "id": str(uuid4()),
                        "name": "Example company",
                        "domain": "example.test",
                    },
                    "score": 27,
                    "rationale": "Topic overlap only.",
                    "evidence": [
                        {
                            "quote": "We are hiring onboarding engineers.",
                            "source_url": "https://example.test/source",
                            "occurred_at": "2026-10-01T12:00:00Z",
                        }
                    ],
                }
            ],
        }


class Sender:
    def __init__(self):
        self.messages = []
        self.fail = False

    def send(self, message):
        self.messages.append(message)
        if self.fail:
            raise OSError("secret SMTP details must not escape")


def fixture():
    store = Store()
    sender = Sender()
    recommendations = Recommendations()
    service = WeeklyDigestService(
        lambda: Work(),
        repository_factory=lambda _: store,
        recommendations=recommendations,
        sender=sender,
        web_origin="https://huginn.example",
        sender_address="weekly@huginn.example",
        signing_key="test-key",
        clock=lambda: NOW,
    )
    return service, store, sender, recommendations


def test_weekly_job_saves_payload_and_uses_existing_ranker_and_link():
    service, store, sender, recommendations = fixture()
    assert service.run()["sent"] == 1
    assert store.states == ["sent"]
    assert recommendations.calls[0][-1] == frozenset((store.company,))
    assert len(store.prepared) == 1
    message = sender.messages[0]
    assert "https://huginn.example/weekly-matches?batch=" in message.body
    assert "/weekly-digest/unsubscribe#user_id=" in message.body
    assert "Example company" in message.body
    assert "confirmed" in message.body
    assert message.message_id.startswith("<weekly-")
    assert service.run()["skipped"] == 1
    assert len(sender.messages) == 1


def test_dry_run_never_generates_reserves_or_sends():
    service, store, sender, recommendations = fixture()
    assert service.run(dry_run=True)["eligible"] == 1
    assert not store.claimed and not sender.messages and not recommendations.calls


def test_uncertain_smtp_outcome_is_recorded_without_automatic_repeat():
    service, store, sender, _ = fixture()
    sender.fail = True
    assert service.run()["unknown"] == 1
    assert store.states == ["unknown"]
    assert service.run()["skipped"] == 1
    assert len(sender.messages) == 1


def test_no_new_recommendations_sends_no_empty_mail():
    service, store, sender, recommendations = fixture()
    recommendations.empty = True
    assert service.run()["empty"] == 1
    assert not sender.messages
    assert store.states == ["empty"]


def test_invalid_strategies_do_not_consume_weekly_reservation():
    service, store, sender, recommendations = fixture()
    recommendations.invalid = True
    assert service.run()["skipped"] == 1
    assert not store.claimed and not store.prepared and not sender.messages
    recommendations.invalid = False
    assert service.run()["sent"] == 1
