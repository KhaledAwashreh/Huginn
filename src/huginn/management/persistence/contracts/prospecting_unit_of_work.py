"""Atomic workflow repositories over the management transaction boundary."""

from typing import Protocol
from uuid import UUID

from huginn.management.persistence.contracts.repositories.assessment_revision import (
    AssessmentRevisionRepository,
)
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.contracts.repositories.business_recommendation_preferences import (
    BusinessRecommendationPreferencesRepository,
)
from huginn.management.persistence.contracts.repositories.command_receipt import (
    CommandReceiptRepository,
)
from huginn.management.persistence.contracts.repositories.offer_cycle import (
    OfferCycleRepository,
)
from huginn.management.persistence.contracts.repositories.prospect import (
    ProspectRepository,
)
from huginn.management.persistence.contracts.repositories.prospect_activity import (
    ProspectActivityRepository,
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


class ProspectingUnitOfWork(UnitOfWorkProtocol, Protocol):
    businesses: BusinessRepository
    business_recommendation_preferences: BusinessRecommendationPreferencesRepository
    recommendations: RecommendationRepository
    recommendation_feedback: RecommendationAssessmentFeedbackRepository
    assessment_revisions: AssessmentRevisionRepository
    offer_cycles: OfferCycleRepository
    prospects: ProspectRepository
    origins: ProspectOriginRepository
    activities: ProspectActivityRepository
    suppression_blocks: SuppressionBlockRepository
    commands: CommandReceiptRepository

    def lock_business_company(self, business_id: UUID, company_id: UUID) -> None:
        """Acquire the shared pair lock, held through this UOW's commit/rollback.

        Every cross-channel writer takes this lock before reading suppression or
        writing an occurrence, origin, prospect, activity or offer claim. SQL
        uniqueness remains a second, database-enforced boundary.

        Reassessment appends a revision then calls `select_current_revision`
        before the same transaction commits. Save/rejection operations similarly
        commit recommendation resolution, prospect/origin/activity or rejection
        block changes together. A stored command receipt contains the committed
        result snapshot/version so a retry does not read later mutable state.
        """
