from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.prospects import ProspectService
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.prospect_activity_occurrence import (
    project_activity_occurrence,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
    PsycopgDatabaseSession,
)
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.repositories.prospect import (
    PostgresProspectRepository,
)
from huginn.management.persistence.repositories.prospect_activity import (
    PostgresProspectActivityRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_prospect,
)
from tests.management.persistence.retained_prospecting_fixtures import (
    generate_retained_brightroom_selection,
    seed_retained_brightroom_context,
)

BASE = datetime.now(UTC) + timedelta(days=1)


def _factory(database_url):
    return ManagementConnectionFactory(database_url, statement_timeout_ms=5000)


def _seed(database_url, *, stage="saved"):
    with psycopg.connect(database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        prospect = valid_prospect(identity, stage=ProspectStage(stage), at=BASE)
        saved = PostgresProspectRepository(PsycopgDatabaseSession(connection)).create(
            prospect
        )
    return identity, saved, Principal(identity.account_id, identity.owner_user_id)


def _read_prospect(database_url, business_id, prospect_id):
    with psycopg.connect(database_url) as connection:
        return PostgresProspectRepository(PsycopgDatabaseSession(connection)).get_owned(
            business_id, prospect_id
        )


def _read_activities(database_url, business_id, prospect_id):
    with psycopg.connect(database_url) as connection:
        return PostgresProspectActivityRepository(
            PsycopgDatabaseSession(connection)
        ).list_owned(business_id, prospect_id)


def test_retained_source_manual_retry_returns_current_state_and_preserves_all_history(
    retained_management_database_url,
    monkeypatch,
):
    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selection = generate_retained_brightroom_selection(context)

    def factory():
        return PostgresProspectingUnitOfWork(context.connection_factory)

    saved = SaveRecommendationService(
        factory, clock=lambda: context.current_time[0]
    ).execute(
        context.principal,
        SaveRecommendationRequest(
            selection.recommendation_id, selection.revision_id, "source-save"
        ),
    )
    service = ProspectService(factory, clock=lambda: context.current_time[0])
    request = {
        "prospect_id": saved.prospect_id,
        "expected_version": saved.prospect_version,
        "replacement_notes": "First memo",
        "occurred_at": context.current_time[0],
        "request_key": "source-note",
    }
    original = service.update_notes(context.principal, **request)
    latest = service.update_notes(
        context.principal,
        prospect_id=saved.prospect_id,
        expected_version=original.prospect.version,
        replacement_notes="Latest memo",
        occurred_at=context.current_time[0],
        request_key="source-note-later",
    )
    tables = (
        "prospects",
        "prospect_activities",
        "prospect_origins",
        "command_receipts",
        "recommendations",
        "assessment_revisions",
    )

    def read_persisted():
        with psycopg.connect(context.database_url) as connection:
            return {
                table: connection.execute(
                    f"SELECT to_jsonb(record) FROM operational.{table} record WHERE business_id=%s ORDER BY to_jsonb(record)",
                    (context.business_id,),
                ).fetchall()
                for table in tables
            }

    before_retry = read_persisted()
    replay = service.update_notes(context.principal, **request)
    assert replay.prospect == latest.prospect
    assert replay.activity == original.activity
    assert read_persisted() == before_retry
    assert replay.prospect.version > original.prospect.version
    with PostgresProspectingUnitOfWork(
        context.connection_factory, read_only=True
    ) as work:
        receipt = work.commands.get_by_key(context.business_id, request["request_key"])
        assert receipt.resource_version == original.prospect.version
        assert receipt.result_snapshot.value == {
            "activity_id": str(original.activity.id)
        }
        origins = work.origins.list_owned(context.business_id, saved.prospect_id)
        assert len(origins) == 1
        assert origins[0].assessment_revision_id == selection.revision_id
        revision = work.assessment_revisions.get_owned(
            context.business_id, selection.recommendation_id, selection.revision_id
        )
        assert context.listing_url in str(revision.evidence_snapshots)
    with pytest.raises(ConflictError):
        service.update_notes(
            context.principal,
            prospect_id=request["prospect_id"],
            expected_version=request["expected_version"],
            replacement_notes="Changed retry",
            occurred_at=request["occurred_at"],
            request_key=request["request_key"],
        )
    with pytest.raises(ConflictError):
        service.update_notes(
            context.principal,
            prospect_id=request["prospect_id"],
            expected_version=request["expected_version"],
            replacement_notes=request["replacement_notes"],
            occurred_at=request["occurred_at"],
            request_key="stale-new-command",
        )
    assert read_persisted() == before_retry


def test_stage_activity_notes_followup_and_correction_history_round_trip(
    management_database_url,
):
    identity, prospect, principal = _seed(management_database_url)
    stage_service = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=1),
    )
    contacted_args = {
        "prospect_id": prospect.id,
        "expected_version": prospect.version,
        "target_stage": ProspectStage("contacted"),
        "occurred_at": BASE - timedelta(days=2),
        "request_key": "stage-contacted",
    }
    contacted = stage_service.change_stage(principal, **contacted_args)
    assert stage_service.change_stage(principal, **contacted_args) == contacted
    assert contacted.activity.occurred_at == BASE - timedelta(days=2)
    assert contacted.activity.recorded_at == BASE + timedelta(minutes=1)
    assert (
        _read_prospect(management_database_url, identity.business_id, prospect.id)
        == contacted.prospect
    )

    conversation = stage_service.change_stage(
        principal,
        prospect_id=prospect.id,
        expected_version=contacted.prospect.version,
        target_stage=ProspectStage("in_conversation"),
        occurred_at=BASE - timedelta(days=1),
        request_key="stage-conversation",
    )
    proposal = stage_service.change_stage(
        principal,
        prospect_id=prospect.id,
        expected_version=conversation.prospect.version,
        target_stage=ProspectStage("proposal_sent"),
        occurred_at=BASE,
        request_key="stage-proposal",
    )
    assert proposal.activity.kind.value == "proposal_sent"
    won = stage_service.change_stage(
        principal,
        prospect_id=prospect.id,
        expected_version=proposal.prospect.version,
        target_stage=ProspectStage("won_client"),
        occurred_at=BASE + timedelta(minutes=1),
        request_key="stage-won",
    )
    proposal_revisited = stage_service.change_stage(
        principal,
        prospect_id=prospect.id,
        expected_version=won.prospect.version,
        target_stage=ProspectStage("proposal_sent"),
        occurred_at=BASE + timedelta(minutes=2),
        request_key="stage-return-to-proposal",
        reason="The client reopened pricing discussion",
    )
    assert proposal_revisited.activity.kind.value == "stage_changed"

    draft_service = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=4),
    )
    draft = draft_service.record_proposal_draft(
        principal,
        prospect_id=prospect.id,
        expected_version=proposal_revisited.prospect.version,
        summary="Scope draft, not sent",
        occurred_at=BASE + timedelta(minutes=2),
        request_key="proposal-draft",
    )
    assert draft.prospect == proposal_revisited.prospect

    notes = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=5),
    )
    note_update = notes.update_notes(
        principal,
        prospect_id=prospect.id,
        expected_version=draft.prospect.version,
        replacement_notes="Replacement memo",
        occurred_at=BASE + timedelta(minutes=3),
        request_key="memo-replace",
    )
    assert note_update.activity.payload.value == {
        "prior": "Initial prospect note",
        "replacement": "Replacement memo",
    }
    note_clear = notes.update_notes(
        principal,
        prospect_id=prospect.id,
        expected_version=note_update.prospect.version,
        replacement_notes="",
        occurred_at=BASE + timedelta(minutes=4),
        request_key="memo-clear",
    )
    assert note_clear.prospect.notes == ""

    follow_up_at = BASE - timedelta(hours=1)
    set_follow_up = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=7),
    ).set_follow_up(
        principal,
        prospect_id=prospect.id,
        expected_version=note_clear.prospect.version,
        follow_up_at=follow_up_at,
        occurred_at=BASE + timedelta(minutes=5),
        request_key="followup-set",
    )
    assert set_follow_up.prospect.follow_up_at == follow_up_at
    clear_follow_up = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=8),
    ).clear_follow_up(
        principal,
        prospect_id=prospect.id,
        expected_version=set_follow_up.prospect.version,
        occurred_at=BASE + timedelta(minutes=6),
        request_key="followup-clear",
    )
    assert clear_follow_up.prospect.follow_up_at is None

    backward = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=9),
    ).change_stage(
        principal,
        prospect_id=prospect.id,
        expected_version=clear_follow_up.prospect.version,
        target_stage=ProspectStage("in_conversation"),
        occurred_at=BASE + timedelta(minutes=7),
        request_key="stage-backward",
        reason="Proposal needs revision",
    )
    close = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=10),
    ).close(
        principal,
        prospect_id=prospect.id,
        expected_version=backward.prospect.version,
        reason="Engagement declined",
        occurred_at=BASE + timedelta(minutes=8),
        request_key="close",
    )
    reopened = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=11),
    ).reopen(
        principal,
        prospect_id=prospect.id,
        expected_version=close.prospect.version,
        occurred_at=BASE + timedelta(minutes=9),
        request_key="reopen",
    )
    assert reopened.prospect.stage == ProspectStage("in_conversation")
    assert reopened.prospect.last_active_stage is None

    corrected = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=12),
    )
    first_correction = corrected.correct_activity_time(
        principal,
        prospect_id=prospect.id,
        expected_version=reopened.prospect.version,
        original_activity_id=proposal.activity.id,
        expected_correction_head_id=None,
        replacement_occurred_at=BASE - timedelta(days=4),
        request_key="correct-proposal-first",
    )
    second_correction = corrected.correct_activity_time(
        principal,
        prospect_id=prospect.id,
        expected_version=reopened.prospect.version,
        original_activity_id=proposal.activity.id,
        expected_correction_head_id=first_correction.activity.id,
        replacement_occurred_at=BASE - timedelta(days=5),
        request_key="correct-proposal-second",
    )

    persisted = _read_activities(
        management_database_url, identity.business_id, prospect.id
    )
    original_proposal = next(
        activity for activity in persisted if activity.id == proposal.activity.id
    )
    correction_rows = tuple(
        activity
        for activity in persisted
        if activity.correction_of_id == proposal.activity.id
    )
    projection = project_activity_occurrence(original_proposal, persisted)
    assert original_proposal.occurred_at == BASE
    assert sorted(
        row.payload.value["correction_sequence"] for row in correction_rows
    ) == [1, 2]
    assert projection.effective_occurred_at == BASE - timedelta(days=5)
    assert projection.correction_head_id == second_correction.activity.id
    assert projection.correction_sequence == 2
    assert (
        _read_prospect(management_database_url, identity.business_id, prospect.id)
        == reopened.prospect
    )
    assert {activity.kind.value for activity in persisted} >= {
        "stage_changed",
        "proposal_sent",
        "proposal_drafted",
        "note_added",
        "follow_up_set",
        "follow_up_cleared",
        "closed",
        "reopened",
        "correction",
    }
    assert [activity.kind.value for activity in persisted].count("proposal_sent") == 1
    assert any(
        activity.kind.value == "stage_changed"
        and activity.payload.value.get("prior_stage") == "won_client"
        and activity.payload.value.get("new_stage") == "proposal_sent"
        and activity.payload.value.get("reason")
        == "The client reopened pricing discussion"
        for activity in persisted
    )
    assert all(
        activity.actor_user_id == identity.owner_user_id for activity in persisted
    )


class _FailingCommands:
    def __init__(self, delegate):
        self._delegate = delegate

    def get_by_key(self, business_id, key):
        return self._delegate.get_by_key(business_id, key)

    def record(self, receipt):
        raise ConflictError("Injected receipt failure")


class _FailingReceiptUnitOfWork(PostgresProspectingUnitOfWork):
    def __enter__(self):
        super().__enter__()
        self.commands = _FailingCommands(self.commands)
        return self


def test_note_and_activity_rollback_with_receipt_failure(management_database_url):
    identity, prospect, principal = _seed(management_database_url)
    before_activities = _read_activities(
        management_database_url, identity.business_id, prospect.id
    )
    service = ProspectService(
        lambda: _FailingReceiptUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=1),
    )
    with pytest.raises(ConflictError, match="Injected receipt failure"):
        service.update_notes(
            principal,
            prospect_id=prospect.id,
            expected_version=1,
            replacement_notes="Must roll back",
            occurred_at=BASE,
            request_key="rollback-note",
        )
    assert (
        _read_prospect(management_database_url, identity.business_id, prospect.id)
        == prospect
    )
    assert (
        _read_activities(management_database_url, identity.business_id, prospect.id)
        == before_activities
    )
    with psycopg.connect(management_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND idempotency_key=%s",
                (identity.business_id, "rollback-note"),
            ).fetchone()[0]
            == 0
        )


def test_foreign_owner_cannot_mutate_prospect_and_stale_version_conflicts(
    management_database_url,
):
    identity, prospect, principal = _seed(management_database_url)
    with psycopg.connect(management_database_url) as connection:
        other_identity = seed_prospecting_owner_company(connection)
    foreign = Principal(other_identity.account_id, other_identity.owner_user_id)
    service = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=1),
    )
    request = {
        "prospect_id": prospect.id,
        "expected_version": 1,
        "target_stage": ProspectStage("contacted"),
        "occurred_at": BASE,
        "request_key": "owned-stage",
    }
    changed = service.change_stage(principal, **request)
    with pytest.raises(ConflictError):
        service.change_stage(
            principal,
            **{**request, "request_key": "stale-stage"},
        )
    with pytest.raises(NotFoundError):
        service.change_stage(foreign, **{**request, "request_key": "foreign-stage"})
    assert (
        _read_prospect(management_database_url, identity.business_id, prospect.id)
        == changed.prospect
    )
    assert (
        len(
            _read_activities(management_database_url, identity.business_id, prospect.id)
        )
        == 1
    )
