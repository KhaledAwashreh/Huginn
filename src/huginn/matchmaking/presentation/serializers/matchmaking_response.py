"""Explicit JSON fields for a single User response."""

from datetime import UTC, datetime
from uuid import UUID

from huginn.matchmaking.application.responses.matchmaking_response import (
    MatchmakingResponse,
)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _uuid(value: UUID) -> str:
    return str(value)


def serialize_matchmaking_response(response: MatchmakingResponse) -> dict[str, object]:
    return {
        "user_id": _uuid(response.user_id),
        "status": response.status.value,
        "cutoff": _timestamp(response.cutoff),
        "as_of": _timestamp(response.as_of),
        "strategies_evaluated": response.strategies_evaluated,
        "strategies_skipped": response.strategies_skipped,
        "unique_candidates_count": response.unique_candidates_count,
        "created_matches": [
            {
                "id": _uuid(match.id),
                "user_id": _uuid(match.user_id),
                "company_id": _uuid(match.company_id),
                "status": match.status.value,
                "notes": match.notes,
                "created_at": _timestamp(match.created_at),
                "updated_at": _timestamp(match.updated_at),
            }
            for match in response.created_matches
        ],
        "existing_matches_skipped_count": response.existing_matches_skipped_count,
        "skipped_strategies": [
            {"strategy_id": _uuid(item.strategy_id), "reason": item.reason.value}
            for item in response.skipped_strategies
        ],
    }
