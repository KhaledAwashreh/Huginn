"""Load and validate a selected revision for an explicit offer command."""

from datetime import datetime
from uuid import UUID

from huginn.management.application.policies.recommendation_geography import (
    resolve_country_evidence,
)
from huginn.management.application.policies.recommendation_offer_selection import (
    offer_selection_inputs_match,
)
from huginn.management.application.protocols.recommendation_generation import (
    RecommendationGenerationSource,
)
from huginn.management.application.read_models.recommendation_offer_selection import (
    RecommendationOfferSelection,
)
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)


def load_current_offer_selection(
    work: ProspectingUnitOfWork,
    source: RecommendationGenerationSource,
    business_id: UUID,
    owner_user_id: UUID,
    recommendation_id: UUID,
    revision_id: UUID,
    as_of: datetime,
) -> RecommendationOfferSelection:
    recommendation = work.recommendations.get_owned(business_id, recommendation_id)
    revision = work.assessment_revisions.get_owned(
        business_id, recommendation_id, revision_id
    )
    if recommendation is None or revision is None:
        raise NotFoundError("Recommendation selection not found")
    if (
        recommendation.status != RecommendationStatus("open")
        or recommendation.current_revision_id != revision.id
        or revision.business_id != business_id
        or revision.company_id != recommendation.company_id
        or revision.assessed_at > as_of
    ):
        raise ConflictError("Recommendation assessment is no longer current")
    company = source.current_company_for_revision(revision, as_of)
    if company is None:
        raise ConflictError("Recommendation evidence is no longer current")
    company = resolve_country_evidence(company)
    profiles = {}
    for association in revision.strategy_assessments:
        profile = source.profile(owner_user_id, association.strategy_id)
        if profile is None:
            raise ConflictError("Recommendation strategy configuration changed")
        profiles[association.strategy_id] = profile
    if not offer_selection_inputs_match(revision, company, profiles):
        raise ConflictError("Recommendation assessment inputs changed")
    return RecommendationOfferSelection(recommendation, revision, company)


def assert_assessed_after_last_cooldown(
    work: ProspectingUnitOfWork,
    business_id: UUID,
    company_id: UUID,
    revision_assessed_at: datetime,
) -> None:
    last_expiry = max(
        (
            block.expires_at
            for block in work.suppression_blocks.list_history(business_id, company_id)
            if block.kind.value == "cooldown" and block.expires_at is not None
        ),
        default=None,
    )
    if last_expiry is not None and revision_assessed_at < last_expiry:
        raise ConflictError(
            "A renewed offer requires an assessment after the previous cooldown"
        )
