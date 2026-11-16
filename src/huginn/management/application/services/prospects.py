"""Cohesive manual pursuit operations; docs/architecture.md section 9."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

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
from huginn.management.application.responses.prospect_command_response import (
    ProspectCommandResponse,
)
from huginn.management.application.services.prospect_command_support import (
    commit_prospect_command,
    ensure_aware,
    make_activity,
    make_command_identity,
    prepare_prospect_command,
)
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.policies.prospect_activity_occurrence import (
    project_activity_occurrence,
)
from huginn.management.domain.policies.prospect_transition import (
    reopen_prospect,
    transition_prospect,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)


class ProspectService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def change_stage(
        self, principal: Principal, request: ChangeProspectStageRequest
    ) -> ProspectCommandResponse:
        scope = "change_prospect_stage"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "target_stage": request.target_stage.value,
                "occurred_at": request.occurred_at.isoformat(),
                "reason": request.reason,
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            if request.target_stage == ProspectStage("closed"):
                raise ConflictError("Closing requires the explicit close command")
            next_stage = transition_prospect(
                prospect.stage, request.target_stage, reason=request.reason
            )
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                stage=next_stage,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, request.expected_version, updated
            )
            kind = (
                "proposal_sent"
                if prospect.stage.value == "in_conversation"
                and next_stage.value == "proposal_sent"
                else "stage_changed"
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                kind,
                request.occurred_at,
                recorded_at,
                {
                    "prior_stage": prospect.stage.value,
                    "new_stage": next_stage.value,
                    "reason": request.reason,
                },
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def close(
        self, principal: Principal, request: CloseProspectRequest
    ) -> ProspectCommandResponse:
        scope = "close_prospect"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "reason": request.reason,
                "occurred_at": request.occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            next_stage = transition_prospect(
                prospect.stage, ProspectStage("closed"), reason=request.reason
            )
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                stage=next_stage,
                last_active_stage=prospect.stage,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, request.expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "closed",
                request.occurred_at,
                recorded_at,
                {
                    "prior_stage": prospect.stage.value,
                    "new_stage": "closed",
                    "reason": request.reason,
                },
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def reopen(
        self, principal: Principal, request: ReopenProspectRequest
    ) -> ProspectCommandResponse:
        scope = "reopen_prospect"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "occurred_at": request.occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            if prospect.last_active_stage is None:
                raise ValidationDomainError(
                    "Closed prospect has no retained active stage"
                )
            next_stage = reopen_prospect(prospect.stage, prospect.last_active_stage)
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                stage=next_stage,
                last_active_stage=None,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, request.expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "reopened",
                request.occurred_at,
                recorded_at,
                {"prior_stage": "closed", "new_stage": next_stage.value},
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def update_notes(
        self, principal: Principal, request: UpdateProspectNotesRequest
    ) -> ProspectCommandResponse:
        scope = "update_prospect_notes"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "replacement_notes": request.replacement_notes,
                "occurred_at": request.occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                notes=request.replacement_notes,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, request.expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "note_added",
                request.occurred_at,
                recorded_at,
                {"prior": prospect.notes, "replacement": request.replacement_notes},
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def set_follow_up(
        self, principal: Principal, request: SetProspectFollowUpRequest
    ) -> ProspectCommandResponse:
        scope = "set_prospect_follow_up"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "follow_up_at": request.follow_up_at.isoformat(),
                "occurred_at": request.occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                follow_up_at=request.follow_up_at,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, request.expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "follow_up_set",
                request.occurred_at,
                recorded_at,
                {
                    "prior": prospect.follow_up_at.isoformat()
                    if prospect.follow_up_at
                    else None,
                    "replacement": request.follow_up_at.isoformat(),
                },
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def clear_follow_up(
        self, principal: Principal, request: ClearProspectFollowUpRequest
    ) -> ProspectCommandResponse:
        scope = "clear_prospect_follow_up"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "occurred_at": request.occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            if prospect.follow_up_at is None:
                raise ConflictError("Prospect has no scheduled follow-up")
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                follow_up_at=None,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, request.expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "follow_up_cleared",
                request.occurred_at,
                recorded_at,
                {"prior": prospect.follow_up_at.isoformat(), "replacement": None},
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def record_proposal_draft(
        self, principal: Principal, request: RecordProposalDraftRequest
    ) -> ProspectCommandResponse:
        scope = "record_proposal_draft"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "summary": request.summary,
                "occurred_at": request.occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "proposal_drafted",
                request.occurred_at,
                recorded_at,
                {"summary": request.summary},
            )
            return commit_prospect_command(
                uow, scope, identity, prospect, activity, recorded_at
            )

    def correct_activity_time(
        self, principal: Principal, request: CorrectProspectActivityTimeRequest
    ) -> ProspectCommandResponse:
        scope = "correct_prospect_activity_time"
        identity = make_command_identity(
            scope,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "original_activity_id": str(request.original_activity_id),
                "expected_correction_head_id": str(request.expected_correction_head_id)
                if request.expected_correction_head_id
                else None,
                "replacement_occurred_at": request.replacement_occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                request.prospect_id,
                request.expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            activities = uow.activities.list_owned(business_id, prospect.id)
            original = next(
                (
                    activity
                    for activity in activities
                    if activity.id == request.original_activity_id
                ),
                None,
            )
            if original is None:
                raise NotFoundError("Original prospect activity not found")
            if original.kind.value == "correction":
                raise ConflictError("A correction must target an original activity")
            projection = project_activity_occurrence(original, activities)
            if projection.correction_head_id != request.expected_correction_head_id:
                raise ConflictError("Activity correction history changed")
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Correction recorded time")
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "correction",
                recorded_at,
                recorded_at,
                {
                    "prior": projection.effective_occurred_at.isoformat(),
                    "replacement": request.replacement_occurred_at.isoformat(),
                    "correction_sequence": projection.correction_sequence + 1,
                },
                correction_of_id=original.id,
            )
            return commit_prospect_command(
                uow, scope, identity, prospect, activity, recorded_at
            )
