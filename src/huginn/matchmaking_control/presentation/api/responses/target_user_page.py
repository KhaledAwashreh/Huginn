from huginn.management.presentation.api.responses.common import PageResponse
from huginn.matchmaking_control.presentation.api.responses.target_user import (
    TargetUserResponse,
)


class TargetUserPageResponse(PageResponse[TargetUserResponse]):
    total_eligible_count: int
