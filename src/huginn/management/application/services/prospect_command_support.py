"""Shared transaction mechanics for manual prospect commands."""

import logging
from datetime import datetime
from uuid import UUID, uuid4

from huginn.management.application.responses.prospect_command_response import (
    ProspectCommandResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.policies.command_retry import validate_command_retry
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

logger = logging.getLogger(__name__)


def make_command_identity(
    scope: str, principal: Principal, request_key: str, payload: dict[str, object]
) -> CommandIdentity:
    return CommandIdentity(
        request_key,
        fingerprint_command_payload(
            scope,
            {"actor_user_id": str(principal.user_id), **payload},
        ),
    )


def replay_command(
    receipt: CommandReceipt | None, scope: str, identity: CommandIdentity
) -> ProspectCommandResponse | None:
    if receipt is None:
        return None
    validate_command_retry(receipt, scope, identity)
    if receipt.resource_kind != "prospect":
        raise ConflictError("Request key was already used for another result")
    return ProspectCommandResponse.from_snapshot(receipt.result_snapshot)


def load_owned_prospect(
    uow: ProspectingUnitOfWork, business_id: UUID, prospect_id: UUID
) -> Prospect:
    prospect = uow.prospects.get_owned(business_id, prospect_id)
    if prospect is None:
        raise NotFoundError("Prospect not found")
    return prospect


def prepare_prospect_command(
    uow: ProspectingUnitOfWork,
    principal: Principal,
    scope: str,
    identity: CommandIdentity,
    prospect_id: UUID,
    expected_version: int,
) -> tuple[Prospect, ProspectCommandResponse | None]:
    business_id = business_id_for_principal(principal, uow.businesses)
    replay = replay_command(
        uow.commands.get_by_key(business_id, identity.key), scope, identity
    )
    if replay is not None:
        return replay.prospect, replay
    initial = load_owned_prospect(uow, business_id, prospect_id)
    uow.lock_business_company(business_id, initial.company_id)
    prospect = load_owned_prospect(uow, business_id, prospect_id)
    replay = replay_command(
        uow.commands.get_by_key(business_id, identity.key), scope, identity
    )
    if replay is not None:
        return replay.prospect, replay
    require_version(prospect, expected_version)
    return prospect, None


def require_version(prospect: Prospect, expected_version: int) -> None:
    if prospect.version != expected_version:
        raise ConflictError("Prospect changed before the command completed")


def make_activity(
    business_id: UUID,
    prospect_id: UUID,
    actor_user_id: UUID,
    kind: str,
    occurred_at: datetime,
    recorded_at: datetime,
    payload: dict[str, object],
    *,
    correction_of_id: UUID | None = None,
) -> ProspectActivity:
    return ProspectActivity(
        uuid4(),
        business_id,
        prospect_id,
        actor_user_id,
        ActivityKind(kind),
        occurred_at,
        recorded_at,
        JsonSnapshot(payload),
        correction_of_id,
    )


def commit_prospect_command(
    uow: ProspectingUnitOfWork,
    scope: str,
    identity: CommandIdentity,
    prospect: Prospect,
    activity: ProspectActivity,
    recorded_at: datetime,
) -> ProspectCommandResponse:
    saved_activity = uow.activities.append_once(
        prospect.business_id,
        prospect.id,
        identity,
        activity,
    )
    response = ProspectCommandResponse(prospect, saved_activity)
    uow.commands.record(
        CommandReceipt(
            prospect.business_id,
            scope,
            identity,
            "prospect",
            prospect.id,
            prospect.version,
            response.snapshot(),
            recorded_at,
        )
    )
    uow.commit()
    logger.info(
        "Prospect command committed scope=%s business=%s prospect=%s activity=%s",
        scope,
        prospect.business_id,
        prospect.id,
        saved_activity.id,
    )
    return response


def ensure_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
