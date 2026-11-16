"""Bounded guarded source context for prospect detail reads."""

from typing import Literal

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.current_company_signal import (
    CurrentCompanySignalResponse,
)


class CurrentSourceContextResponse(ResponseModel):
    signals: list[CurrentCompanySignalResponse]
    has_more: bool
    evidence_state: Literal["current", "changed", "unavailable", "not_assessed"]
