from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class SkippedStrategyResultResponse(ResponseModel):
    strategy_id: UUID
    reason: str
