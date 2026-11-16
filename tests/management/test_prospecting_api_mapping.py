from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.presentation.api.prospecting_mapping import (
    assessment_revision_response,
    prospect_response,
    recommendation_response,
    suppression_response,
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
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)
from tests.management.persistence.prospecting_fixtures import (
    ProspectingIdentity,
    valid_assessment_revision,
    valid_prospect,
    valid_prospect_activity,
    valid_prospect_origin,
    valid_recommendation,
)


def _base():
    identity = ProspectingIdentity(uuid4(), uuid4(), uuid4(), uuid4())
    recommendation = valid_recommendation(identity)
    revision = valid_assessment_revision(identity, recommendation)
    prospect = valid_prospect(identity)
    company = CurrentCompany(
        id=identity.company_id,
        name="Northstar Labs",
        domain="northstar.example",
        business_sector=("Research", "Data"),
        country="US",
        company_scale="11-50",
        company_status="active",
    )
    return identity, recommendation, revision, prospect, company


def test_revision_mapper_preserves_every_snapshot_and_lineage_value():
    identity, recommendation, revision, _, _ = _base()

    response = assessment_revision_response(revision)

    assert response.id == revision.id
    assert response.recommendation_id == recommendation.id
    assert response.business_id == identity.business_id
    assert response.company_id == identity.company_id
    assert response.revision_number == revision.revision_number
    assert response.assessed_at == revision.assessed_at
    assert response.assessed_by_user_id == identity.owner_user_id
    assert (
        response.professional_profile_snapshot
        == revision.professional_profile_snapshot.to_json_object()
    )
    assert response.evidence_snapshots == [
        item.to_json_object() for item in revision.evidence_snapshots
    ]
    assert response.evidence_observation_ids == list(revision.evidence_observation_ids)
    assert response.policy_versions == list(revision.policy_versions)
    assert (
        response.strategy_assessments[0].strategy_snapshot
        == revision.strategy_assessments[0].strategy_snapshot.to_json_object()
    )
    assert (
        response.strategy_assessments[0].assessment_snapshot
        == revision.strategy_assessments[0].assessment_snapshot.to_json_object()
    )


def test_recommendation_mapper_flattens_status_and_exposes_company_eligibility_and_blocks():
    identity, recommendation, revision, prospect, company = _base()
    now = datetime.now(UTC)
    block = SuppressionBlock(
        id=uuid4(),
        business_id=identity.business_id,
        company_id=identity.company_id,
        kind=SuppressionKind("pause"),
        created_at=now,
        created_by_user_id=identity.owner_user_id,
        expires_at=now + timedelta(days=7),
        version=3,
    )
    view = RecommendationView(
        recommendation=recommendation,
        company=company,
        assessment=revision,
        prospect=prospect,
        selection_state=BusinessCompanyState(paused_until=block.expires_at),
        read_at=now,
        evidence_state="changed",
        active_blocks=(block,),
    )

    response = recommendation_response(view)

    assert response.id == recommendation.id
    assert response.business_id == identity.business_id
    assert response.company_id == identity.company_id
    assert response.status == "open"
    assert response.version == recommendation.version
    assert response.company.name == company.name
    assert response.company.name == company.name
    assert response.company.domain == company.domain
    assert response.company.business_sector == list(company.business_sector)
    assert response.assessment.id == revision.id
    assert response.current_eligibility == view.current_eligibility == "blocked"
    assert response.selection_blockers == list(view.selection_blockers)
    assert response.evidence_state == "changed"
    assert response.active_blocks[0].id == block.id
    assert response.active_blocks[0].kind == "pause"
    assert response.active_blocks[0].version == 3


def test_suppression_mapper_exposes_company_block_identity_and_remaining_eligibility():
    identity, _, _, prospect, company = _base()
    now = datetime.now(UTC)
    block = SuppressionBlock(
        id=uuid4(),
        business_id=identity.business_id,
        company_id=identity.company_id,
        kind=SuppressionKind("rejection"),
        created_at=now,
        created_by_user_id=identity.owner_user_id,
        reason="Not relevant",
        version=2,
    )
    view = ManageableSuppressionView(
        company=company,
        active_blocks=(block,),
        prospect=prospect,
        selection_state=BusinessCompanyState(rejected=True, has_relationship=True),
        read_at=now,
    )

    response = suppression_response(view)

    assert response.company_id == identity.company_id
    assert response.company.name == company.name
    assert response.active_blocks[0].id == block.id
    assert response.active_blocks[0].version == 2
    assert response.selection_blockers == list(view.selection_blockers)
    assert response.prospect.id == prospect.id
    assert response.read_at == now


def test_prospect_detail_projects_effective_time_and_correction_head_without_dropping_raw_history():
    identity, recommendation, revision, prospect, company = _base()
    origin = valid_prospect_origin(identity, recommendation, revision, prospect)
    origin_view = ProspectOriginView(origin, recommendation, revision)
    original = valid_prospect_activity(
        identity, prospect, at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    correction_one = ProspectActivity(
        id=uuid4(),
        business_id=identity.business_id,
        prospect_id=prospect.id,
        actor_user_id=identity.owner_user_id,
        kind=ActivityKind("correction"),
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        recorded_at=datetime(2026, 1, 2, tzinfo=UTC),
        payload=JsonSnapshot(
            {
                "prior": "2026-01-01T00:00:00+00:00",
                "replacement": "2025-12-31T00:00:00+00:00",
                "correction_sequence": 1,
            }
        ),
        correction_of_id=original.id,
    )
    correction_two = ProspectActivity(
        id=uuid4(),
        business_id=identity.business_id,
        prospect_id=prospect.id,
        actor_user_id=identity.owner_user_id,
        kind=ActivityKind("correction"),
        occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        recorded_at=datetime(2026, 1, 3, tzinfo=UTC),
        payload=JsonSnapshot(
            {
                "prior": "2025-12-31T00:00:00+00:00",
                "replacement": "2025-12-30T00:00:00+00:00",
                "correction_sequence": 2,
            }
        ),
        correction_of_id=original.id,
    )
    view = ProspectView(
        prospect,
        company,
        (origin_view,),
        (original, correction_one, correction_two),
    )

    response = prospect_response(view)

    assert response.id == prospect.id
    assert response.company_id == identity.company_id
    assert response.stage == "saved"
    assert response.version == prospect.version
    assert response.origins[0].assessment_revision_id == revision.id
    assert response.activities[0].kind == "note_added"
    assert response.activities[0].effective_occurred_at == datetime(
        2025, 12, 30, tzinfo=UTC
    )
    assert response.activities[0].correction_head_id == correction_two.id
    assert response.activities[0].correction_sequence == 2
    assert response.activities[1].correction_of_id == original.id
    assert response.activities[2].correction_of_id == original.id
    assert response.activities[0].payload == original.payload.to_json_object()


def test_response_schemas_constrain_current_eligibility_and_closed_last_active_stage():
    recommendation_schema = RecommendationResponse.model_json_schema()
    assert recommendation_schema["properties"]["current_eligibility"]["enum"] == [
        "historical",
        "blocked",
        "unavailable",
        "not_reassessed",
    ]

    for response_model in (ProspectResponse, ProspectSummaryResponse):
        property_schema = response_model.model_json_schema()["properties"][
            "last_active_stage"
        ]
        assert {
            value
            for branch in property_schema["anyOf"]
            for value in branch.get("enum", [])
        } == {"saved", "contacted", "in_conversation", "proposal_sent"}
        assert any(branch.get("type") == "null" for branch in property_schema["anyOf"])


def test_prospect_command_mapper_preserves_fresh_and_replayed_http_output():
    from huginn.management.application.responses.prospect_command_response import (
        ProspectCommandResponse as CommandResult,
    )
    from huginn.management.presentation.api import prospecting_mapping

    identity, _, _, prospect, _ = _base()
    activity = valid_prospect_activity(identity, prospect)
    result = CommandResult(prospect, activity)
    mapper = getattr(prospecting_mapping, "prospect_command_response", None)
    assert mapper is not None, "Commands need a typed presentation mapper"
    replay = CommandResult.from_snapshot(result.snapshot())
    import json

    from huginn.management.presentation.api.responses.prospect_command import (
        ProspectCommandResponse,
    )

    expected = ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    ).model_dump(mode="json")
    assert mapper(result).model_dump(mode="json") == expected
    assert mapper(replay).model_dump(mode="json") == expected


def test_recommendation_maps_exact_displayed_assessment_presentation():
    identity, recommendation, revision, _, company = _base()
    presented_at = datetime.now(UTC)
    view = RecommendationView(
        recommendation,
        company,
        revision,
        None,
        BusinessCompanyState(),
        presented_at,
        "current",
        assessment_presented_at=presented_at,
    )
    assert recommendation_response(view).assessment_presented_at == presented_at


def test_prospect_current_sources_are_separate_from_immutable_origins():
    from huginn.management.application.read_models.current_company_signal import (
        CurrentCompanySignal,
    )
    from huginn.management.application.read_models.current_source_context import (
        CurrentSourceContext,
    )

    identity, recommendation, revision, prospect, company = _base()
    origin = ProspectOriginView(
        valid_prospect_origin(identity, recommendation, revision, prospect),
        recommendation,
        revision,
    )
    now = datetime.now(UTC)
    signal = CurrentCompanySignal(
        uuid4(),
        "directory",
        "eu_startups",
        "https://example.test/current",
        "New current evidence",
        None,
        now,
        now,
        uuid4(),
        now,
        "directory_context",
        "not_applicable",
    )
    view = ProspectView(
        prospect,
        company,
        (origin,),
        (),
        CurrentSourceContext((signal,), False, "changed"),
    )
    response = prospect_response(view)
    assert response.current_source_context.evidence_state == "changed"
    assert (
        response.current_source_context.signals[0].observation_id
        == signal.observation_id
    )
    assert response.current_source_context.signals[0].observed_at == now
    assert (
        response.current_source_context.signals[0].description == "New current evidence"
    )
    assert response.origins[0].assessment.evidence_snapshots == [
        item.to_json_object() for item in revision.evidence_snapshots
    ]
    assert (
        prospect_response(
            ProspectView(prospect, company, (origin,))
        ).current_source_context
        is None
    )
