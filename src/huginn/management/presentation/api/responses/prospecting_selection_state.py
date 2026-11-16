"""Typed current Business/Company eligibility state, without capability tokens."""

from datetime import datetime

from huginn.management.presentation.api.responses.common import ResponseModel


class ProspectingSelectionStateResponse(ResponseModel):
    first_presented_at: datetime | None
    cooldown_until: datetime | None
    paused_until: datetime | None
    paused_indefinitely: bool
    rejected: bool
    has_relationship: bool
    pending_delivery: bool
    uncertain_delivery: bool
