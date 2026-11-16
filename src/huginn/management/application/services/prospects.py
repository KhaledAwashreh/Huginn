"""Cohesive manual pursuit operations; docs/architecture.md section 9."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

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
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        target_stage: ProspectStage,
        occurred_at: datetime,
        request_key: str,
        reason: str | None = None,
    ) -> ProspectCommandResponse:
        _validate_command(prospect_id, expected_version, occurred_at, request_key)
        if not isinstance(target_stage, ProspectStage):
            raise ValidationDomainError("Target stage must use its domain value")
        if reason is not None and not isinstance(reason, str):
            raise ValidationDomainError("Stage reason must be text")
        scope = "change_prospect_stage"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "target_stage": target_stage.value,
                "occurred_at": occurred_at.isoformat(),
                "reason": reason,
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            if target_stage == ProspectStage("closed"):
                raise ConflictError("Closing requires the explicit close command")
            next_stage = transition_prospect(
                prospect.stage, target_stage, reason=reason
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
                business_id, prospect.id, expected_version, updated
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
                occurred_at,
                recorded_at,
                {
                    "prior_stage": prospect.stage.value,
                    "new_stage": next_stage.value,
                    "reason": reason,
                },
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def close(
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        reason: str,
        occurred_at: datetime,
        request_key: str,
    ) -> ProspectCommandResponse:
        _validate_command(prospect_id, expected_version, occurred_at, request_key)
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationDomainError("Closing a prospect requires a reason")
        scope = "close_prospect"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "reason": reason,
                "occurred_at": occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            next_stage = transition_prospect(
                prospect.stage, ProspectStage("closed"), reason=reason
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
                business_id, prospect.id, expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "closed",
                occurred_at,
                recorded_at,
                {
                    "prior_stage": prospect.stage.value,
                    "new_stage": "closed",
                    "reason": reason,
                },
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def reopen(
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        occurred_at: datetime,
        request_key: str,
    ) -> ProspectCommandResponse:
        _validate_command(prospect_id, expected_version, occurred_at, request_key)
        scope = "reopen_prospect"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "occurred_at": occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
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
                business_id, prospect.id, expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "reopened",
                occurred_at,
                recorded_at,
                {"prior_stage": "closed", "new_stage": next_stage.value},
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def update_notes(
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        replacement_notes: str,
        occurred_at: datetime,
        request_key: str,
    ) -> ProspectCommandResponse:
        _validate_command(prospect_id, expected_version, occurred_at, request_key)
        if not isinstance(replacement_notes, str):
            raise ValidationDomainError("Prospect notes must be text")
        scope = "update_prospect_notes"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "replacement_notes": replacement_notes,
                "occurred_at": occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                notes=replacement_notes,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "note_added",
                occurred_at,
                recorded_at,
                {"prior": prospect.notes, "replacement": replacement_notes},
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def set_follow_up(
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        follow_up_at: datetime,
        occurred_at: datetime,
        request_key: str,
    ) -> ProspectCommandResponse:
        _validate_identity(prospect_id, expected_version)
        _ensure_aware(follow_up_at, "Follow-up times must include a timezone")
        _ensure_aware(occurred_at, "Follow-up times must include a timezone")
        _ensure_key(request_key)
        scope = "set_prospect_follow_up"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "follow_up_at": follow_up_at.isoformat(),
                "occurred_at": occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            recorded_at = self._clock()
            ensure_aware(recorded_at, "Prospect command time")
            updated = replace(
                prospect,
                follow_up_at=follow_up_at,
                updated_at=recorded_at,
                version=prospect.version + 1,
            )
            updated = uow.prospects.update_owned(
                business_id, prospect.id, expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "follow_up_set",
                occurred_at,
                recorded_at,
                {
                    "prior": prospect.follow_up_at.isoformat()
                    if prospect.follow_up_at
                    else None,
                    "replacement": follow_up_at.isoformat(),
                },
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def clear_follow_up(
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        occurred_at: datetime,
        request_key: str,
    ) -> ProspectCommandResponse:
        _validate_command(prospect_id, expected_version, occurred_at, request_key)
        scope = "clear_prospect_follow_up"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "occurred_at": occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
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
                business_id, prospect.id, expected_version, updated
            )
            activity = make_activity(
                business_id,
                prospect.id,
                principal.user_id,
                "follow_up_cleared",
                occurred_at,
                recorded_at,
                {"prior": prospect.follow_up_at.isoformat(), "replacement": None},
            )
            return commit_prospect_command(
                uow, scope, identity, updated, activity, recorded_at
            )

    def record_proposal_draft(
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        summary: str,
        occurred_at: datetime,
        request_key: str,
    ) -> ProspectCommandResponse:
        _validate_command(prospect_id, expected_version, occurred_at, request_key)
        if not isinstance(summary, str) or not summary.strip():
            raise ValidationDomainError("Proposal draft summary is required")
        scope = "record_proposal_draft"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "summary": summary,
                "occurred_at": occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
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
                occurred_at,
                recorded_at,
                {"summary": summary},
            )
            return commit_prospect_command(
                uow, scope, identity, prospect, activity, recorded_at
            )

    def correct_activity_time(
        self,
        principal: Principal,
        *,
        prospect_id: UUID,
        expected_version: int,
        original_activity_id: UUID,
        expected_correction_head_id: UUID | None,
        replacement_occurred_at: datetime,
        request_key: str,
    ) -> ProspectCommandResponse:
        if not isinstance(prospect_id, UUID) or not isinstance(
            original_activity_id, UUID
        ):
            raise ValidationDomainError(
                "Prospect and original activity IDs must be UUIDs"
            )
        if type(expected_version) is not int or expected_version < 1:
            raise ValidationDomainError("Expected prospect version must be positive")
        if expected_correction_head_id is not None and not isinstance(
            expected_correction_head_id, UUID
        ):
            raise ValidationDomainError("Expected correction head must be a UUID")
        _ensure_aware(
            replacement_occurred_at,
            "Corrected occurrence time must include a timezone",
        )
        _ensure_key(request_key)
        scope = "correct_prospect_activity_time"
        identity = make_command_identity(
            scope,
            principal,
            request_key,
            {
                "prospect_id": str(prospect_id),
                "expected_version": expected_version,
                "original_activity_id": str(original_activity_id),
                "expected_correction_head_id": str(expected_correction_head_id)
                if expected_correction_head_id
                else None,
                "replacement_occurred_at": replacement_occurred_at.isoformat(),
            },
        )
        with self._uow_factory() as uow:
            prospect, replay = prepare_prospect_command(
                uow,
                principal,
                scope,
                identity,
                prospect_id,
                expected_version,
            )
            if replay is not None:
                return replay
            business_id = prospect.business_id
            activities = uow.activities.list_owned(business_id, prospect.id)
            original = next(
                (
                    activity
                    for activity in activities
                    if activity.id == original_activity_id
                ),
                None,
            )
            if original is None:
                raise NotFoundError("Original prospect activity not found")
            if original.kind.value == "correction":
                raise ConflictError("A correction must target an original activity")
            projection = project_activity_occurrence(original, activities)
            if projection.correction_head_id != expected_correction_head_id:
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
                    "replacement": replacement_occurred_at.isoformat(),
                    "correction_sequence": projection.correction_sequence + 1,
                },
                correction_of_id=original.id,
            )
            return commit_prospect_command(
                uow, scope, identity, prospect, activity, recorded_at
            )


def _validate_command(
    prospect_id: UUID,
    expected_version: int,
    occurred_at: datetime,
    request_key: str,
    *,
    time_message: str = "Activity occurrence time must include a timezone",
) -> None:
    _validate_identity(prospect_id, expected_version)
    _ensure_aware(occurred_at, time_message)
    _ensure_key(request_key)


def _validate_identity(prospect_id: UUID, expected_version: int) -> None:
    if not isinstance(prospect_id, UUID):
        raise ValidationDomainError("Prospect ID must be a UUID")
    if type(expected_version) is not int or expected_version < 1:
        raise ValidationDomainError("Expected prospect version must be positive")


def _ensure_aware(value: datetime, message: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError(message)


def _ensure_key(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationDomainError("Request key is required")
