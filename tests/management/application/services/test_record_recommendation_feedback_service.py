from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.requests.record_recommendation_feedback_request import (
    RecordRecommendationFeedbackRequest,
)
from huginn.management.application.services.record_recommendation_feedback_service import (
    RecordRecommendationFeedbackService,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.business import Business
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def revision_for(recommendation: Recommendation, revision_number: int = 1):
    strategy = StrategyAssessmentSnapshot(
        uuid4(), uuid4(), uuid4(), {}, {}, {}, {"eligible": True}
    )
    return AssessmentRevision(
        uuid4(),
        recommendation.id,
        recommendation.business_id,
        recommendation.company_id,
        revision_number,
        NOW,
        (strategy,),
        {"professional_summary": "Independent consultant"},
        (),
        (),
        ("ranking.v1",),
        assessed_by_user_id=uuid4(),
    )


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
            uuid4(),
            self.business.id,
            uuid4(),
            RecommendationStatus("open"),
            NOW,
            NOW,
        )
        self.revision = revision_for(self.recommendation)
        self.revisions = {self.revision.id: self.revision}
        self.feedback = []
        self.receipts = {}
        self.in_flight_receipts = {}
        self.prospects = [(uuid4(), "untouched")]
        self.suppressions = [(uuid4(), "untouched")]
        self.configuration = {"icp_id": str(uuid4()), "value": "unchanged"}
        self.ranking = {"policy": "ranking.v1"}
        self.commits = 0
        self.after_lock = lambda: None

    def request(self, *, key="feedback-one", revision_id=None, feedback=None):
        return RecordRecommendationFeedbackRequest(
            self.recommendation.id,
            revision_id or self.revision.id,
            key,
            feedback or RecommendationFeedback("useful"),
        )

    def service(self):
        return RecordRecommendationFeedbackService(
            lambda: MemoryUow(self), clock=lambda: NOW
        )


class MemoryUow:
    connection = None

    def __init__(self, store):
        self.store = store
        self.businesses = SimpleNamespace(
            get_by_owner_user_id=lambda owner_id: (
                store.business if owner_id == store.principal.user_id else None
            )
        )
        self.recommendations = SimpleNamespace(get_owned=self.get_recommendation)
        self.assessment_revisions = SimpleNamespace(get_owned=self.get_revision)
        self.recommendation_feedback = SimpleNamespace(append=self.append_feedback)
        self.commands = SimpleNamespace(
            get_by_key=self.get_receipt, record=self.record_receipt
        )

    def __enter__(self):
        self.snapshot = (
            list(self.store.feedback),
            dict(self.store.receipts),
            self.store.recommendation,
        )
        self.committed = False
        return self

    def __exit__(self, *_):
        if not self.committed:
            self.rollback()
        return False

    def commit(self):
        self.committed = True
        self.store.commits += 1

    def rollback(self):
        feedback, receipts, recommendation = self.snapshot
        self.store.feedback[:] = feedback
        self.store.receipts.clear()
        self.store.receipts.update(receipts)
        self.store.recommendation = recommendation

    def lock_business_company(self, business_id, company_id):
        assert business_id == self.store.business.id
        assert company_id == self.store.recommendation.company_id
        self.store.after_lock()

    def get_recommendation(self, business_id, recommendation_id):
        recommendation = self.store.recommendation
        return (
            recommendation
            if (recommendation.business_id, recommendation.id)
            == (business_id, recommendation_id)
            else None
        )

    def get_revision(self, business_id, recommendation_id, revision_id):
        revision = self.store.revisions.get(revision_id)
        return (
            revision
            if revision is not None
            and (revision.business_id, revision.recommendation_id)
            == (business_id, recommendation_id)
            else None
        )

    def append_feedback(self, feedback):
        self.store.feedback.append(feedback)
        return feedback

    def get_receipt(self, business_id, key):
        return self.store.receipts.get((business_id, key))

    def record_receipt(self, receipt):
        key = (receipt.business_id, receipt.identity.key)
        if key in self.store.in_flight_receipts:
            raise ConflictError("Concurrent request key belongs to another command")
        if key in self.store.receipts:
            raise ConflictError("Request key is already recorded")
        self.store.receipts[key] = receipt
        return receipt


def test_feedback_is_attributed_to_historic_shown_revision_without_changing_state():
    store = Store()
    earlier = store.revision
    current = revision_for(store.recommendation, revision_number=2)
    store.revisions[current.id] = current
    store.recommendation = replace(
        store.recommendation,
        current_revision_id=current.id,
        status=RecommendationStatus("converted"),
        resolved_at=NOW,
        resolved_by_user_id=store.principal.user_id,
        version=2,
    )
    feedback = RecommendationFeedback(
        "useful", ("service_fit",), next_step="save", outcome="won"
    )
    before = (
        store.recommendation,
        list(store.prospects),
        list(store.suppressions),
        dict(store.configuration),
        dict(store.ranking),
    )

    result = store.service().execute(
        store.principal,
        store.request(revision_id=earlier.id, feedback=feedback),
    )

    assert result.feedback.business_id == store.business.id
    assert result.feedback.actor_user_id == store.principal.user_id
    assert result.feedback.recommendation_id == store.recommendation.id
    assert result.feedback.assessment_revision_id == earlier.id
    assert result.feedback.feedback is feedback
    assert len(store.feedback) == 1
    assert store.commits == 1
    assert (
        store.recommendation,
        store.prospects,
        store.suppressions,
        store.configuration,
        store.ranking,
    ) == before


def test_useful_without_an_action_records_feedback_without_saving_a_prospect():
    store = Store()
    before_prospects = list(store.prospects)

    result = store.service().execute(store.principal, store.request())

    assert result.feedback.feedback == RecommendationFeedback("useful")
    assert store.prospects == before_prospects
    assert store.recommendation.status.value == "open"
    assert len(store.feedback) == 1


@pytest.mark.parametrize("next_step", ["save", "contact", "skip"])
@pytest.mark.parametrize("outcome", ["not_relevant", "won"])
def test_reported_outcome_and_next_step_remain_feedback_only(next_step, outcome):
    store = Store()
    before_recommendation = store.recommendation
    before_prospects = list(store.prospects)
    before_suppressions = list(store.suppressions)
    before_configuration = dict(store.configuration)
    before_ranking = dict(store.ranking)
    result = store.service().execute(
        store.principal,
        store.request(
            feedback=RecommendationFeedback(
                "useful", next_step=next_step, outcome=outcome
            )
        ),
    )

    assert result.feedback.feedback.next_step == next_step
    assert result.feedback.feedback.outcome == outcome
    assert store.recommendation is before_recommendation
    assert store.prospects == before_prospects
    assert store.suppressions == before_suppressions
    assert store.configuration == before_configuration
    assert store.ranking == before_ranking


def test_same_intent_retry_replays_immutable_result_after_current_state_changes():
    store = Store()
    request = store.request()
    first = store.service().execute(store.principal, request)
    store.recommendation = replace(
        store.recommendation,
        status=RecommendationStatus("rejected"),
        resolved_at=NOW,
        resolved_by_user_id=store.principal.user_id,
        version=2,
    )
    store.revisions[store.revision.id] = replace(store.revision, revision_number=2)

    replay = store.service().execute(store.principal, request)

    assert replay == first
    assert len(store.feedback) == 1
    assert store.commits == 1


def test_same_key_with_changed_feedback_or_scope_conflicts_before_append():
    store = Store()
    store.service().execute(store.principal, store.request())
    changed = store.request(
        feedback=RecommendationFeedback("not_useful", outcome="won")
    )

    with pytest.raises(ConflictError):
        store.service().execute(store.principal, changed)

    assert len(store.feedback) == 1
    assert store.commits == 1


def test_same_key_receipt_from_another_command_scope_conflicts():
    store = Store()
    request = store.request()
    store.service().execute(store.principal, request)
    receipt_key = (store.business.id, request.request_key)
    store.receipts[receipt_key] = replace(
        store.receipts[receipt_key], scope="save_recommendation"
    )

    with pytest.raises(ConflictError):
        store.service().execute(store.principal, request)

    assert len(store.feedback) == 1
    assert store.commits == 1


def test_rejects_foreign_or_mismatched_revision_without_writes():
    store = Store()
    foreign = Principal(uuid4(), uuid4())

    with pytest.raises(NotFoundError):
        store.service().execute(foreign, store.request())

    store.revisions[store.revision.id] = replace(store.revision, company_id=uuid4())
    with pytest.raises(NotFoundError):
        store.service().execute(store.principal, store.request())

    assert store.feedback == []
    assert store.commits == 0


def test_revalidates_recommendation_and_revision_after_shared_pair_lock():
    store = Store()
    store.after_lock = lambda: setattr(
        store,
        "revisions",
        {store.revision.id: replace(store.revision, company_id=uuid4())},
    )

    with pytest.raises(NotFoundError):
        store.service().execute(store.principal, store.request())

    assert store.feedback == []
    assert store.commits == 0


def test_different_company_same_key_receipt_conflict_rolls_back_feedback_append():
    store = Store()
    other_recommendation = replace(store.recommendation, company_id=uuid4())
    other_identity = CommandIdentity("feedback-one", "a" * 64)
    concurrent_receipt = CommandReceipt(
        store.business.id,
        "save_recommendation",
        other_identity,
        "prospect",
        uuid4(),
        1,
        {
            "recommendation_id": str(other_recommendation.id),
            "company_id": str(other_recommendation.company_id),
        },
        NOW,
    )
    store.in_flight_receipts[(store.business.id, "feedback-one")] = concurrent_receipt

    with pytest.raises(ConflictError):
        store.service().execute(store.principal, store.request())

    assert store.feedback == []
    assert store.receipts == {}
    assert store.commits == 0
