"""Append a correction for the occurrence time of one original activity."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from huginn.management.application.requests.correct_prospect_activity_time_request import (
    CorrectProspectActivityTimeRequest,
)
from huginn.management.application.responses.prospect_command_response import (
    ProspectCommandResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.application.services.prospect_command_support import (
    commit_prospect_command,
    ensure_aware,
    load_owned_prospect,
    lock_and_reload_prospect,
    make_activity,
    make_command_identity,
    replay_command,
    require_version,
)
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.prospect_activity_occurrence import (
    project_activity_occurrence,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

logger = logging.getLogger(__name__)
_SCOPE = "correct_prospect_activity_time"


class CorrectProspectActivityTimeService:
    def __init__(
        self, unit_of_work_factory: Callable[[], ProspectingUnitOfWork], *, clock=None
    ):
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: CorrectProspectActivityTimeRequest
    ) -> ProspectCommandResponse:
        identity = make_command_identity(
            _SCOPE,
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
            business_id = business_id_for_principal(principal, uow.businesses)
            replay = replay_command(
                uow.commands.get_by_key(business_id, identity.key), _SCOPE, identity
            )
            if replay is not None:
                return replay
            prospect = load_owned_prospect(uow, business_id, request.prospect_id)
            prospect = lock_and_reload_prospect(uow, business_id, prospect.id)
            replay = replay_command(
                uow.commands.get_by_key(business_id, identity.key), _SCOPE, identity
            )
            if replay is not None:
                return replay
            require_version(prospect, request.expected_version)
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
                uow, _SCOPE, identity, prospect, activity, recorded_at
            )
