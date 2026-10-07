"""Explicit JSON fields for a batch response."""

from datetime import UTC, datetime

from huginn.matchmaking.application.responses.batch_matchmaking_response import (
    BatchMatchmakingResponse,
)
from huginn.matchmaking.presentation.serializers.matchmaking_response import (
    serialize_matchmaking_response,
)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def serialize_batch_matchmaking_response(
    response: BatchMatchmakingResponse,
) -> dict[str, object]:
    return {
        "cutoff": _timestamp(response.cutoff),
        "as_of": _timestamp(response.as_of),
        "responses": [
            serialize_matchmaking_response(item) for item in response.responses
        ],
        "failures": [
            {"user_id": str(item.user_id), "reason": item.reason.value}
            for item in response.failures
        ],
    }
