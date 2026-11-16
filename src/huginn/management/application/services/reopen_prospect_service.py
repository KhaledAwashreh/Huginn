"""Explicitly reopen a closed prospect at its last active stage."""

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from huginn.management.application.requests.reopen_prospect_request import (
    ReopenProspectRequest,
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
from huginn.management.domain.policies.prospect_transition import reopen_prospect
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

logger = logging.getLogger(__name__)
_SCOPE = "reopen_prospect"


class ReopenProspectService:
    def __init__(
        self, unit_of_work_factory: Callable[[], ProspectingUnitOfWork], *, clock=None
    ):
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: ReopenProspectRequest
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
            if prospect.last_active_stage is None:
                from huginn.management.domain.errors.errors import ValidationDomainError

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
                uow, _SCOPE, identity, updated, activity, recorded_at
            )
