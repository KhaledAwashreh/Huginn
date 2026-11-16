from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.domain.entities.business import Business
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.origin_append_result import (
    OriginAppendResult,
)
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)

NOW = datetime(2026, 11, 14, tzinfo=UTC)


class Store:
    def __init__(self):
        self.principal = Principal(uuid4(), uuid4())
        self.business = Business(
            uuid4(),
            self.principal.user_id,
            None,
            None,
            None,
            None,
            None,
            None,
            NOW,
            NOW,
        )
        self.recommendation = Recommendation(
            uuid4(), self.business.id, uuid4(), RecommendationStatus("open"), NOW, NOW
        )
        self.revision = SimpleNamespace(
            id=uuid4(),
            recommendation_id=self.recommendation.id,
            business_id=self.business.id,
            company_id=self.recommendation.company_id,
        )
        self.prospects = {}
        self.origins = {}
        self.activities = {}
        self.receipts = {}
        self.commits = 0
        self.fail_receipt = False
        self.after_lock = lambda: None

    def request(self, key="save-one", revision_id=None):
        return SaveRecommendationRequest(
            self.recommendation.id, revision_id or self.revision.id, key
        )

    def service(self):
        return SaveRecommendationService(lambda: MemoryUow(self), clock=lambda: NOW)


class MemoryUow:
    connection = None

    def __init__(self, store):
        self.store = store
        self.businesses = SimpleNamespace(
            get_by_owner_user_id=lambda user_id: (
                store.business if user_id == store.principal.user_id else None
            )
        )
        self.recommendations = SimpleNamespace(
            get_owned=self.get_recommendation, resolve_owned=self.resolve
        )
        self.assessment_revisions = SimpleNamespace(get_owned=self.get_revision)
        self.prospects = SimpleNamespace(
            get_by_business_company=self.get_prospect, create=self.create_prospect
        )
        self.origins = SimpleNamespace(append_if_absent=self.append_origin)
        self.activities = SimpleNamespace(append_once=self.append_activity)
        self.commands = SimpleNamespace(
            get_by_key=self.get_receipt, record=self.record_receipt
        )

    def __enter__(self):
        self.snapshot = (
            self.store.recommendation,
            *(
                getattr(self.store, name).copy()
                for name in ("prospects", "origins", "activities", "receipts")
            ),
        )
        self.committed = False
        return self

    def __exit__(self, *_):
        if not self.committed:
            self.rollback()
        return False

    def rollback(self):
        self.store.recommendation = self.snapshot[0]
        for name, value in zip(
            ("prospects", "origins", "activities", "receipts"),
            self.snapshot[1:],
            strict=True,
        ):
            setattr(self.store, name, value)

    def commit(self):
        self.committed = True
        self.store.commits += 1

    def lock_business_company(self, business_id, company_id):
        assert business_id == self.store.business.id
        assert company_id == self.store.revision.company_id
        self.store.after_lock()

    def get_recommendation(self, business_id, recommendation_id):
        rec = self.store.recommendation
        return (
            rec
            if rec and rec.business_id == business_id and rec.id == recommendation_id
            else None
        )

    def get_revision(self, business_id, recommendation_id, revision_id):
        rev = self.store.revision
        return (
            rev
            if (rev.business_id, rev.recommendation_id, rev.id)
            == (business_id, recommendation_id, revision_id)
            else None
        )

    def resolve(
        self,
        business_id,
        recommendation_id,
        expected_version,
        status,
        actor_user_id,
        resolved_at,
        reason,
    ):
        rec = self.get_recommendation(business_id, recommendation_id)
        assert rec.version == expected_version
        self.store.recommendation = replace(
            rec,
            status=status,
            version=rec.version + 1,
            updated_at=resolved_at,
            resolved_at=resolved_at,
            resolved_by_user_id=actor_user_id,
            resolution_reason=reason,
        )
        return self.store.recommendation

    def get_prospect(self, business_id, company_id):
        return self.store.prospects.get((business_id, company_id))

    def create_prospect(self, prospect):
        return self.store.prospects.setdefault(
            (prospect.business_id, prospect.company_id), prospect
        )

    def append_origin(self, origin):
        key = (
            origin.business_id,
            origin.prospect_id,
            origin.recommendation_id,
            origin.assessment_revision_id,
        )
        if key in self.store.origins:
            return OriginAppendResult(self.store.origins[key], False)
        self.store.origins[key] = origin
        return OriginAppendResult(origin, True)

    def append_activity(self, business_id, prospect_id, identity, activity):
        assert (activity.business_id, activity.prospect_id) == (
            business_id,
            prospect_id,
        )
        return self.store.activities.setdefault((business_id, identity.key), activity)

    def get_receipt(self, business_id, key):
        return self.store.receipts.get((business_id, key))

    def record_receipt(self, receipt):
        if self.store.fail_receipt:
            raise ConflictError("Concurrent request key belongs to other intent")
        self.store.receipts[(receipt.business_id, receipt.identity.key)] = receipt
        return receipt


def test_save_exact_shown_revision_converts_once_and_records_attributed_origin():
    store = Store()
    result = store.service().execute(store.principal, store.request())
    assert result.prospect_stage == "saved"
    assert result.company_id == store.revision.company_id
    assert result.assessment_revision_id == store.revision.id
    assert result.recommendation_status == "converted"
    assert result.prospect_version == 1
    assert store.recommendation.status.value == "converted"
    assert len(store.origins) == len(store.activities) == len(store.receipts) == 1
    origin = next(iter(store.origins.values()))
    activity = next(iter(store.activities.values()))
    assert (
        origin.created_by_user_id == activity.actor_user_id == store.principal.user_id
    )
    assert origin.assessment_revision_id == store.revision.id
    assert activity.kind.value == "prospect_saved"
    assert activity.occurred_at == activity.recorded_at == NOW
    assert activity.payload.to_json_object()["origin_id"] == str(origin.id)
    assert store.commits == 1


def test_existing_relationship_stage_notes_and_follow_up_are_preserved():
    store = Store()
    existing = Prospect(
        uuid4(),
        store.business.id,
        store.revision.company_id,
        ProspectStage("proposal_sent"),
        NOW,
        NOW,
        version=7,
        notes="Retain this",
        follow_up_at=NOW,
    )
    store.prospects[(existing.business_id, existing.company_id)] = existing
    result = store.service().execute(store.principal, store.request())
    assert result.prospect_id == existing.id
    assert result.prospect_stage == "proposal_sent"
    assert result.prospect_version == 7
    assert next(iter(store.prospects.values())) == existing


def test_lost_response_replay_returns_original_snapshot_after_later_stage_change():
    store = Store()
    original = store.service().execute(store.principal, store.request())
    key = (store.business.id, store.revision.company_id)
    store.prospects[key] = replace(
        store.prospects[key], stage=ProspectStage("contacted"), version=2
    )
    replay = store.service().execute(store.principal, store.request())
    assert replay == original
    assert replay.prospect_stage == "saved"
    assert store.prospects[key].stage.value == "contacted"
    assert len(store.activities) == len(store.origins) == 1
    assert store.commits == 1


def test_distinct_request_key_for_same_origin_does_not_duplicate_save_activity():
    store = Store()
    first = store.service().execute(store.principal, store.request())
    second = store.service().execute(store.principal, store.request("save-two"))
    assert first == second
    assert len(store.prospects) == len(store.origins) == len(store.activities) == 1
    assert len(store.receipts) == 2


def test_historical_rejected_save_preserves_original_resolution():
    store = Store()
    store.recommendation = replace(
        store.recommendation,
        status=RecommendationStatus("rejected"),
        resolved_at=NOW,
        resolved_by_user_id=store.principal.user_id,
        resolution_reason="Original rejection",
        version=3,
    )
    before = store.recommendation
    result = store.service().execute(store.principal, store.request())
    assert store.recommendation == before
    assert result.recommendation_status == "rejected"
    assert result.prospect_stage == "saved"
    assert len(store.origins) == len(store.activities) == 1


@pytest.mark.parametrize("invalid", ["owner", "revision", "company"])
def test_foreign_or_mismatched_membership_has_no_writes(invalid):
    store = Store()
    principal, request = store.principal, store.request()
    if invalid == "owner":
        principal = Principal(uuid4(), uuid4())
    elif invalid == "revision":
        request = store.request(revision_id=uuid4())
    else:
        store.revision.company_id = uuid4()
    with pytest.raises(NotFoundError):
        store.service().execute(principal, request)
    assert not store.prospects and not store.activities and not store.receipts
    assert store.commits == 0


def test_membership_is_revalidated_after_pair_lock():
    store = Store()
    store.after_lock = lambda: setattr(store, "recommendation", None)
    with pytest.raises(NotFoundError):
        store.service().execute(store.principal, store.request())
    assert not store.prospects and not store.origins and not store.activities
    assert store.commits == 0


def test_changed_intent_under_used_key_is_conflict_without_partial_writes():
    store = Store()
    store.service().execute(store.principal, store.request())
    with pytest.raises(ConflictError):
        store.service().execute(store.principal, store.request(revision_id=uuid4()))
    assert (
        len(store.prospects)
        == len(store.origins)
        == len(store.activities)
        == len(store.receipts)
        == 1
    )
    assert store.commits == 1


def test_simulated_receipt_uniqueness_loss_rolls_back_entire_transition():
    store = Store()
    before = store.recommendation
    store.fail_receipt = True
    with pytest.raises(ConflictError):
        store.service().execute(store.principal, store.request())
    assert store.recommendation == before
    assert (
        not store.prospects
        and not store.origins
        and not store.activities
        and not store.receipts
    )
    assert store.commits == 0


def test_request_key_from_other_command_scope_cannot_be_reused():
    store = Store()
    store.service().execute(store.principal, store.request())
    key = (store.business.id, "save-one")
    store.receipts[key] = replace(store.receipts[key], scope="later")
    with pytest.raises(ConflictError):
        store.service().execute(store.principal, store.request())
    assert len(store.activities) == len(store.origins) == len(store.receipts) == 1
    assert store.commits == 1


def test_invalid_clock_does_not_commit_partial_state():
    store = Store()
    service = SaveRecommendationService(
        lambda: MemoryUow(store), clock=lambda: NOW.replace(tzinfo=None)
    )
    with pytest.raises(ValueError, match="timezone"):
        service.execute(store.principal, store.request())
    assert not store.prospects and not store.activities and not store.receipts
    assert store.commits == 0
