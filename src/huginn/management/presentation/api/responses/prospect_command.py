"""Immutable command result; read detail for the latest canonical state/history."""

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.prospect_command_activity import (
    ProspectCommandActivityResponse,
)
from huginn.management.presentation.api.responses.prospecting_prospect_summary import (
    ProspectSummaryResponse,
)


class ProspectCommandResponse(ResponseModel):
    prospect: ProspectSummaryResponse
    activity: ProspectCommandActivityResponse
