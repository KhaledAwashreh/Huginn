from dataclasses import dataclass
from datetime import datetime

from huginn.matchmaking.application.responses.matchmaking_response import (
    MatchmakingResponse,
)
from huginn.matchmaking.application.responses.user_failure import UserFailure


@dataclass(frozen=True)
class BatchMatchmakingResponse:
    cutoff: datetime
    as_of: datetime
    responses: tuple[MatchmakingResponse, ...]
    failures: tuple[UserFailure, ...]
