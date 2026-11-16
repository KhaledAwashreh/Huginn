from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.domain.errors.errors import ConflictError, NotFoundError

NOW = datetime(2026, 11, 16, tzinfo=UTC)


@pytest.mark.parametrize("phase", ["prepare", "authorize"])
@pytest.mark.parametrize(
    "error_type", [RuntimeError, TypeError, ConflictError, NotFoundError]
)
def test_selection_only_skips_expected_conflicts(
    phase, error_type, monkeypatch, caplog
):
    subscription = DigestSubscription(uuid4(), uuid4(), "verified@example.test", NOW)
    company_id, recommendation_id, revision_id, cycle_id, content_id = (
        uuid4() for _ in range(5)
    )
    delivery = SimpleNamespace(
        id=uuid4(),
        business_id=subscription.business_id,
        version=2,
        state="preparing",
        current_content_id=content_id,
    )
    reference = SimpleNamespace(
        recommendation_id=recommendation_id, revision_id=revision_id
    )
    member = SimpleNamespace(
        company_id=company_id,
        recommendation_id=recommendation_id,
        assessment_revision_id=revision_id,
        offer_cycle_id=cycle_id,
    )
    content = SimpleNamespace(
        id=content_id, business_id=subscription.business_id, members=(member,)
    )
    cycle = SimpleNamespace(
        status=SimpleNamespace(value="preparing"), claim_token="token"
    )
    settlements, abandoned, sent = [], [], []

    class Work:
        connection = object()
        recommendations = SimpleNamespace(
            get_owned=lambda *args: SimpleNamespace(
                company_id=company_id, current_revision_id=revision_id
            )
        )
        assessment_revisions = SimpleNamespace(
            get_owned=lambda *args: SimpleNamespace(id=revision_id)
        )
        offer_cycles = SimpleNamespace(
            get_owned=lambda *args: cycle,
            abandon_preparing=lambda *args: abandoned.append(args),
        )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def commit(self):
            pass

        def lock_business_company(self, *args):
            pass

    access = SimpleNamespace(
        list_eligible=lambda limit: (subscription,),
        get_for_authorization=lambda business_id: subscription,
    )
    repository = SimpleNamespace(
        reserve=lambda *args: delivery,
        get_for_update=lambda *args: delivery,
        settle=lambda *args: settlements.append(args[3]),
    )

    class Service(WeeklyDigestService):
        def _has_valid_active_profile(self, subscription):
            return True

        def _prepare_content(self, *args):
            if phase == "authorize":
                return content, {cycle_id: "token"}
            return super()._prepare_content(*args)

    def fail_selection(*args):
        raise error_type("selection failed")

    monkeypatch.setattr(
        "huginn.management.application.services.weekly_digest.load_current_offer_selection",
        fail_selection,
    )
    service = Service(
        Work,
        subscription_access_factory=lambda work: access,
        delivery_repository_factory=lambda work: repository,
        content_repository_factory=lambda work: None,
        source_factory=lambda connection: object(),
        generation=SimpleNamespace(
            execute_weekly=lambda business_id: SimpleNamespace(
                business_id=business_id, references=(reference,)
            )
        ),
        renderer=object(),
        sender=SimpleNamespace(send=lambda message: sent.append(message)),
        sender_address="weekly@example.test",
        clock=lambda: NOW,
    )
    result = service.run()

    unexpected = error_type in {RuntimeError, TypeError}
    assert result["failed"] == int(unexpected)
    assert result["skipped"] == int(not unexpected)
    assert settlements == ["preparation_failed" if unexpected else "suppressed"]
    assert len(abandoned) == int(phase == "authorize")
    assert sent == []
    if unexpected:
        assert "Weekly digest processing failed" in caplog.text
