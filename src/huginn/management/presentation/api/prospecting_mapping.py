"""Map prospecting read models and domain values to explicit API responses."""

from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.application.read_models.manageable_suppression_view import (
    ManageableSuppressionView,
)
from huginn.management.application.read_models.prospect_origin_view import (
    ProspectOriginView,
)
from huginn.management.application.read_models.prospect_view import ProspectView
from huginn.management.application.read_models.recommendation_view import (
    RecommendationView,
)
from huginn.management.application.responses.prospect_command_response import (
    ProspectCommandResponse as ProspectCommandResult,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.policies.prospect_activity_occurrence import (
    project_activity_occurrence,
)
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)
from huginn.management.presentation.api.responses.current_company import (
    CurrentCompanyResponse,
)
from huginn.management.presentation.api.responses.prospect_command import (
    ProspectCommandResponse,
)
from huginn.management.presentation.api.responses.prospect_command_activity import (
    ProspectCommandActivityResponse,
)
from huginn.management.presentation.api.responses.prospecting_activity import (
    ProspectActivityResponse,
)
from huginn.management.presentation.api.responses.prospecting_assessment_revision import (
    AssessmentRevisionResponse,
)
from huginn.management.presentation.api.responses.prospecting_origin import (
    ProspectOriginResponse,
)
from huginn.management.presentation.api.responses.prospecting_prospect import (
    ProspectResponse,
)
from huginn.management.presentation.api.responses.prospecting_prospect_summary import (
    ProspectSummaryResponse,
)
from huginn.management.presentation.api.responses.prospecting_recommendation import (
    RecommendationResponse,
)
from huginn.management.presentation.api.responses.prospecting_selection_state import (
    ProspectingSelectionStateResponse,
)
from huginn.management.presentation.api.responses.prospecting_strategy_assessment import (
    StrategyAssessmentResponse,
)
from huginn.management.presentation.api.responses.prospecting_suppression import (
    SuppressionResponse,
)
from huginn.management.presentation.api.responses.prospecting_suppression_block import (
    SuppressionBlockResponse,
)


def assessment_revision_response(
    revision: AssessmentRevision,
) -> AssessmentRevisionResponse:
    return AssessmentRevisionResponse(
        id=revision.id,
        recommendation_id=revision.recommendation_id,
        business_id=revision.business_id,
        company_id=revision.company_id,
        revision_number=revision.revision_number,
        assessed_at=revision.assessed_at,
        assessed_by_user_id=revision.assessed_by_user_id,
        strategy_assessments=[
            _strategy_assessment(item) for item in revision.strategy_assessments
        ],
        professional_profile_snapshot=revision.professional_profile_snapshot.to_json_object(),
        evidence_snapshots=[
            item.to_json_object() for item in revision.evidence_snapshots
        ],
        evidence_observation_ids=list(revision.evidence_observation_ids),
        policy_versions=list(revision.policy_versions),
        evaluation_seed=revision.evaluation_seed,
    )


def recommendation_response(view: RecommendationView) -> RecommendationResponse:
    recommendation = view.recommendation
    return RecommendationResponse(
        id=recommendation.id,
        business_id=recommendation.business_id,
        company_id=recommendation.company_id,
        status=recommendation.status.value,
        created_at=recommendation.created_at,
        updated_at=recommendation.updated_at,
        current_revision_id=recommendation.current_revision_id,
        first_presented_at=recommendation.first_presented_at,
        resolved_at=recommendation.resolved_at,
        resolved_by_user_id=recommendation.resolved_by_user_id,
        resolution_reason=recommendation.resolution_reason,
        version=recommendation.version,
        company=_company_response(view.company),
        assessment=(
            assessment_revision_response(view.assessment)
            if view.assessment is not None
            else None
        ),
        prospect=_prospect_entity(view.prospect) if view.prospect is not None else None,
        selection_state=_selection_state(view.selection_state),
        selection_blockers=list(view.selection_blockers),
        current_eligibility=view.current_eligibility,
        read_at=view.read_at,
        evidence_state=view.evidence_state,
        active_blocks=[_suppression_block(block) for block in view.active_blocks],
    )


def suppression_response(view: ManageableSuppressionView) -> SuppressionResponse:
    return SuppressionResponse(
        company_id=view.company.id,
        company=_company_response(view.company),
        active_blocks=[_suppression_block(block) for block in view.active_blocks],
        prospect=_prospect_entity(view.prospect) if view.prospect is not None else None,
        selection_state=_selection_state(view.selection_state),
        selection_blockers=list(view.selection_blockers),
        read_at=view.read_at,
    )


def prospect_response(view: ProspectView) -> ProspectResponse:
    prospect = view.prospect
    history = view.activities
    return ProspectResponse(
        id=prospect.id,
        business_id=prospect.business_id,
        company_id=prospect.company_id,
        stage=prospect.stage.value,
        created_at=prospect.created_at,
        updated_at=prospect.updated_at,
        version=prospect.version,
        notes=prospect.notes,
        follow_up_at=prospect.follow_up_at,
        last_active_stage=(
            prospect.last_active_stage.value
            if prospect.last_active_stage is not None
            else None
        ),
        company=_company_response(view.company),
        origins=[_prospect_origin(origin) for origin in view.origins],
        activities=(
            [_prospect_activity(activity, history) for activity in history]
            if history is not None
            else None
        ),
    )


def _strategy_assessment(
    value: StrategyAssessmentSnapshot,
) -> StrategyAssessmentResponse:
    return StrategyAssessmentResponse(
        strategy_id=value.strategy_id,
        offering_id=value.offering_id,
        ideal_client_profile_id=value.ideal_client_profile_id,
        strategy_snapshot=value.strategy_snapshot.to_json_object(),
        offering_snapshot=value.offering_snapshot.to_json_object(),
        ideal_client_profile_snapshot=value.ideal_client_profile_snapshot.to_json_object(),
        assessment_snapshot=value.assessment_snapshot.to_json_object(),
    )


def _company_response(company: CurrentCompany) -> CurrentCompanyResponse:
    return CurrentCompanyResponse(
        name=company.name,
        domain=company.domain,
        business_sector=(
            list(company.business_sector)
            if company.business_sector is not None
            else None
        ),
        country=company.country,
        company_scale=company.company_scale,
        company_status=company.company_status,
    )


def _selection_state(value) -> ProspectingSelectionStateResponse:
    return ProspectingSelectionStateResponse(
        first_presented_at=value.first_presented_at,
        cooldown_until=value.cooldown_until,
        paused_until=value.paused_until,
        paused_indefinitely=value.paused_indefinitely,
        rejected=value.rejected,
        has_relationship=value.has_relationship,
        pending_delivery=value.pending_delivery,
        uncertain_delivery=value.uncertain_delivery,
    )


def _suppression_block(block: SuppressionBlock) -> SuppressionBlockResponse:
    return SuppressionBlockResponse(
        id=block.id,
        business_id=block.business_id,
        company_id=block.company_id,
        kind=block.kind.value,
        created_at=block.created_at,
        effective_at=block.effective_at,
        created_by_user_id=block.created_by_user_id,
        expires_at=block.expires_at,
        cleared_at=block.cleared_at,
        cleared_by_user_id=block.cleared_by_user_id,
        reason=block.reason,
        version=block.version,
    )


def _prospect_entity(prospect: Prospect) -> ProspectSummaryResponse:
    return ProspectSummaryResponse(
        id=prospect.id,
        business_id=prospect.business_id,
        company_id=prospect.company_id,
        stage=prospect.stage.value,
        created_at=prospect.created_at,
        updated_at=prospect.updated_at,
        version=prospect.version,
        notes=prospect.notes,
        follow_up_at=prospect.follow_up_at,
        last_active_stage=(
            prospect.last_active_stage.value
            if prospect.last_active_stage is not None
            else None
        ),
    )


def _prospect_origin(value: ProspectOriginView) -> ProspectOriginResponse:
    origin: ProspectOrigin = value.origin
    return ProspectOriginResponse(
        id=origin.id,
        business_id=origin.business_id,
        company_id=origin.company_id,
        prospect_id=origin.prospect_id,
        recommendation_id=origin.recommendation_id,
        assessment_revision_id=origin.assessment_revision_id,
        created_by_user_id=origin.created_by_user_id,
        created_at=origin.created_at,
        recommendation_status=value.recommendation.status.value,
        recommendation_version=value.recommendation.version,
        assessment=assessment_revision_response(value.assessment),
    )


def _prospect_activity(
    activity: ProspectActivity,
    history: tuple[ProspectActivity, ...],
) -> ProspectActivityResponse:
    effective_occurred_at = activity.occurred_at
    correction_head_id = None
    correction_sequence = 0
    if activity.kind.value != "correction":
        occurrence = project_activity_occurrence(activity, history)
        effective_occurred_at = occurrence.effective_occurred_at
        correction_head_id = occurrence.correction_head_id
        correction_sequence = occurrence.correction_sequence
    return ProspectActivityResponse(
        id=activity.id,
        business_id=activity.business_id,
        prospect_id=activity.prospect_id,
        actor_user_id=activity.actor_user_id,
        kind=activity.kind.value,
        occurred_at=activity.occurred_at,
        recorded_at=activity.recorded_at,
        payload=activity.payload.to_json_object(),
        correction_of_id=activity.correction_of_id,
        effective_occurred_at=effective_occurred_at,
        correction_head_id=correction_head_id,
        correction_sequence=correction_sequence,
    )


def prospect_command_response(result: ProspectCommandResult) -> ProspectCommandResponse:
    activity = result.activity
    return ProspectCommandResponse(
        prospect=_prospect_entity(result.prospect),
        activity=ProspectCommandActivityResponse(
            id=activity.id,
            business_id=activity.business_id,
            prospect_id=activity.prospect_id,
            actor_user_id=activity.actor_user_id,
            kind=activity.kind.value,
            occurred_at=activity.occurred_at,
            recorded_at=activity.recorded_at,
            payload=activity.payload.to_json_object(),
            correction_of_id=activity.correction_of_id,
        ),
    )
