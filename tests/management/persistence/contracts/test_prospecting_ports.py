from datetime import datetime
from typing import get_type_hints
from uuid import UUID

from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.value_objects.origin_append_result import (
    OriginAppendResult,
)
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.management.persistence.contracts.repositories.assessment_revision import (
    AssessmentRevisionRepository,
)
from huginn.management.persistence.contracts.repositories.command_receipt import (
    CommandReceiptRepository,
)
from huginn.management.persistence.contracts.repositories.offer_cycle import (
    OfferCycleRepository,
)
from huginn.management.persistence.contracts.repositories.prospect_origin import (
    ProspectOriginRepository,
)
from huginn.management.persistence.contracts.repositories.recommendation import (
    RecommendationRepository,
)
from huginn.management.persistence.contracts.repositories.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedbackRepository,
)
from huginn.management.persistence.contracts.repositories.suppression_block import (
    SuppressionBlockRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


def test_prospecting_unit_of_work_extends_existing_transaction_boundary():
    assert getattr(ProspectingUnitOfWork, "_is_protocol", False)
    for name in ("__enter__", "__exit__", "commit", "rollback"):
        assert callable(getattr(ProspectingUnitOfWork, name))
        assert name in UnitOfWorkProtocol.__dict__
    assert callable(ProspectingUnitOfWork.lock_business_company)
    assert "held through" in ProspectingUnitOfWork.lock_business_company.__doc__


def test_command_receipt_lookup_is_by_business_and_key_alone():
    hints = get_type_hints(CommandReceiptRepository.get_by_key)
    assert hints["business_id"] is UUID
    assert hints["idempotency_key"] is str
    assert (
        "immutable committed outcome snapshot"
        in CommandReceiptRepository.record.__doc__
    )


def test_origin_append_returns_insert_result_for_exact_origin_deduplication():
    hints = get_type_hints(ProspectOriginRepository.append_if_absent)
    assert hints["origin"] is ProspectOrigin
    assert hints["return"] is OriginAppendResult


def test_revision_history_and_selection_are_distinct_atomic_protocol_operations():
    assert callable(AssessmentRevisionRepository.list_history)
    assert callable(AssessmentRevisionRepository.append)
    assert callable(RecommendationRepository.select_current_revision)
    assert (
        "same UOW transaction"
        in RecommendationRepository.select_current_revision.__doc__
    )


def test_offer_retry_lookup_uses_request_key_only_and_unknown_resolution_has_actual_handoff_time():
    hints = get_type_hints(OfferCycleRepository.get_by_request_key)
    assert "identity" not in hints
    assert (
        get_type_hints(OfferCycleRepository.resolve_unknown)["presented_at"]
        == datetime | None
    )


def test_suppression_history_can_be_read_and_one_versioned_block_cleared():
    assert callable(SuppressionBlockRepository.list_history)
    hints = get_type_hints(SuppressionBlockRepository.clear_one)
    assert hints["expected_version"] is int


def test_revision_feedback_port_is_revision_and_business_attributed():
    assert callable(RecommendationAssessmentFeedbackRepository.list_for_revision)
    assert callable(RecommendationAssessmentFeedbackRepository.append)
    assert (
        "exact shown revision"
        in RecommendationAssessmentFeedbackRepository.append.__doc__
    )
