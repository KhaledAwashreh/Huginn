"""Project active Business/Company blocks into recommendation eligibility."""

from datetime import datetime

from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)


def remaining_recommendation_blockers(
    blocks: tuple[SuppressionBlock, ...],
    prospect: Prospect | None,
    pending_offer,
    *,
    at: datetime,
) -> tuple[str, ...]:
    active = tuple(block for block in blocks if block.is_active_at(at))
    cooldowns = tuple(
        block.expires_at
        for block in active
        if block.kind.value == "cooldown" and block.expires_at is not None
    )
    pauses = tuple(block for block in active if block.kind.value == "pause")
    finite_pauses = tuple(
        block.expires_at for block in pauses if block.expires_at is not None
    )
    pending_status = pending_offer.status.value if pending_offer is not None else None
    state = BusinessCompanyState(
        cooldown_until=max(cooldowns) if cooldowns else None,
        paused_until=max(finite_pauses) if finite_pauses else None,
        paused_indefinitely=any(block.expires_at is None for block in pauses),
        rejected=any(block.kind.value == "rejection" for block in active),
        has_relationship=prospect is not None,
        pending_delivery=pending_status in {"preparing", "sending"},
        uncertain_delivery=pending_status == "unknown",
    )
    return assess_recommendation_eligibility(state, at).blockers
