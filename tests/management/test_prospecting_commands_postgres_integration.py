from dataclasses import replace
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from huginn.management.application.requests.change_prospect_stage_request import (
    ChangeProspectStageRequest,
)
from huginn.management.application.requests.clear_prospect_follow_up_request import (
    ClearProspectFollowUpRequest,
)
from huginn.management.application.requests.close_prospect_request import (
    CloseProspectRequest,
)
from huginn.management.application.requests.correct_prospect_activity_time_request import (
    CorrectProspectActivityTimeRequest,
)
from huginn.management.application.requests.record_proposal_draft_request import (
    RecordProposalDraftRequest,
)
from huginn.management.application.requests.reopen_prospect_request import (
    ReopenProspectRequest,
)
from huginn.management.application.requests.set_prospect_follow_up_request import (
    SetProspectFollowUpRequest,
)
from huginn.management.application.requests.update_prospect_notes_request import (
    UpdateProspectNotesRequest,
)
from huginn.management.application.services.prospects import ProspectService
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


def test_stage_activity_notes_followup_and_correction_history_round_trip(
    management_database_url,
):
    identity, prospect, principal = _seed(management_database_url)
    stage_service = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=1),
    )
    contacted_request = ChangeProspectStageRequest(
        prospect.id,
        prospect.version,
        ProspectStage("contacted"),
        BASE - timedelta(days=2),
        "stage-contacted",
    )
    contacted = stage_service.change_stage(principal, contacted_request)
    assert stage_service.change_stage(principal, contacted_request) == contacted
    assert contacted.activity.occurred_at == BASE - timedelta(days=2)
    assert contacted.activity.recorded_at == BASE + timedelta(minutes=1)
    assert (
        _read_prospect(management_database_url, identity.business_id, prospect.id)
        == contacted.prospect
    )

    conversation = stage_service.change_stage(
        principal,
        ChangeProspectStageRequest(
            prospect.id,
            contacted.prospect.version,
            ProspectStage("in_conversation"),
            BASE - timedelta(days=1),
            "stage-conversation",
        ),
    )
    proposal = stage_service.change_stage(
        principal,
        ChangeProspectStageRequest(
            prospect.id,
            conversation.prospect.version,
            ProspectStage("proposal_sent"),
            BASE,
            "stage-proposal",
        ),
    )
    assert proposal.activity.kind.value == "proposal_sent"
    won = stage_service.change_stage(
        principal,
        ChangeProspectStageRequest(
            prospect.id,
            proposal.prospect.version,
            ProspectStage("won_client"),
            BASE + timedelta(minutes=1),
            "stage-won",
        ),
    )
    proposal_revisited = stage_service.change_stage(
        principal,
        ChangeProspectStageRequest(
            prospect.id,
            won.prospect.version,
            ProspectStage("proposal_sent"),
            BASE + timedelta(minutes=2),
            "stage-return-to-proposal",
            "The client reopened pricing discussion",
        ),
    )
    assert proposal_revisited.activity.kind.value == "stage_changed"

    draft_service = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=4),
    )
    draft = draft_service.record_proposal_draft(
        principal,
        RecordProposalDraftRequest(
            prospect.id,
            proposal_revisited.prospect.version,
            "Scope draft, not sent",
            BASE + timedelta(minutes=2),
            "proposal-draft",
        ),
    )
    assert draft.prospect == proposal_revisited.prospect

    notes = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=5),
    )
    note_update = notes.update_notes(
        principal,
        UpdateProspectNotesRequest(
            prospect.id,
            draft.prospect.version,
            "Replacement memo",
            BASE + timedelta(minutes=3),
            "memo-replace",
        ),
    )
    assert note_update.activity.payload.value == {
        "prior": "Initial prospect note",
        "replacement": "Replacement memo",
    }
    note_clear = notes.update_notes(
        principal,
        UpdateProspectNotesRequest(
            prospect.id,
            note_update.prospect.version,
            "",
            BASE + timedelta(minutes=4),
            "memo-clear",
        ),
    )
    assert note_clear.prospect.notes == ""

    follow_up_at = BASE - timedelta(hours=1)
    set_follow_up = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=7),
    ).set_follow_up(
        principal,
        SetProspectFollowUpRequest(
            prospect.id,
            note_clear.prospect.version,
            follow_up_at,
            BASE + timedelta(minutes=5),
            "followup-set",
        ),
    )
    assert set_follow_up.prospect.follow_up_at == follow_up_at
    clear_follow_up = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=8),
    ).clear_follow_up(
        principal,
        ClearProspectFollowUpRequest(
            prospect.id,
            set_follow_up.prospect.version,
            BASE + timedelta(minutes=6),
            "followup-clear",
        ),
    )
    assert clear_follow_up.prospect.follow_up_at is None

    backward = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=9),
    ).change_stage(
        principal,
        ChangeProspectStageRequest(
            prospect.id,
            clear_follow_up.prospect.version,
            ProspectStage("in_conversation"),
            BASE + timedelta(minutes=7),
            "stage-backward",
            "Proposal needs revision",
        ),
    )
    close = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=10),
    ).close(
        principal,
        CloseProspectRequest(
            prospect.id,
            backward.prospect.version,
            "Engagement declined",
            BASE + timedelta(minutes=8),
            "close",
        ),
    )
    reopened = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=11),
    ).reopen(
        principal,
        ReopenProspectRequest(
            prospect.id,
            close.prospect.version,
            BASE + timedelta(minutes=9),
            "reopen",
        ),
    )
    assert reopened.prospect.stage == ProspectStage("in_conversation")
    assert reopened.prospect.last_active_stage is None

    corrected = ProspectService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: BASE + timedelta(minutes=12),
    )
    first_correction = corrected.correct_activity_time(
        principal,
        CorrectProspectActivityTimeRequest(
            prospect.id,
            reopened.prospect.version,
            proposal.activity.id,
            None,
            BASE - timedelta(days=4),
            "correct-proposal-first",
        ),
    )
    second_correction = corrected.correct_activity_time(
        principal,
        CorrectProspectActivityTimeRequest(
            prospect.id,
            reopened.prospect.version,
            proposal.activity.id,
            first_correction.activity.id,
            BASE - timedelta(days=5),
            "correct-proposal-second",
        ),
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
            UpdateProspectNotesRequest(
                prospect.id, 1, "Must roll back", BASE, "rollback-note"
            ),
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
    request = ChangeProspectStageRequest(
        prospect.id, 1, ProspectStage("contacted"), BASE, "owned-stage"
    )
    changed = service.change_stage(principal, request)
    with pytest.raises(ConflictError):
        service.change_stage(
            principal,
            replace(request, request_key="stale-stage"),
        )
    with pytest.raises(NotFoundError):
        service.change_stage(foreign, replace(request, request_key="foreign-stage"))
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
