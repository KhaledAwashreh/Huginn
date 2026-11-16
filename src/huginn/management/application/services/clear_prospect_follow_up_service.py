"""Explicitly clear a scheduled follow-up without other pursuit effects."""

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from huginn.management.application.requests.clear_prospect_follow_up_request import (
    ClearProspectFollowUpRequest,
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
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

logger = logging.getLogger(__name__)
_SCOPE = "clear_prospect_follow_up"


class ClearProspectFollowUpService:
    def __init__(
        self, unit_of_work_factory: Callable[[], ProspectingUnitOfWork], *, clock=None
    ):
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: ClearProspectFollowUpRequest
    ) -> ProspectCommandResponse:
        identity = make_command_identity(
            _SCOPE,
            principal,
            request.request_key,
            {
                "prospect_id": str(request.prospect_id),
                "expected_version": request.expected_version,
                "occurred_at": request.occurred_at.isoformat(),
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
                uow, _SCOPE, identity, updated, activity, recorded_at
            )
