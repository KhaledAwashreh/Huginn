from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class TargetUserResponse(ResponseModel):
    id: UUID
    username: str
    first_name: str
    last_name: str
    has_active_strategies: bool
