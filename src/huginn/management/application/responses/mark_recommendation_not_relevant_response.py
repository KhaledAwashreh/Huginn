"""Committed outcome of an explicit rejection decision."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True, slots=True)
class MarkRecommendationNotRelevantResponse:
    recommendation_id: UUID
    recommendation_version: int
    recommendation_status: str
    suppression_block_id: UUID
    resolved_at: datetime
    reason: str | None
    remaining_blockers: tuple[str, ...]

    def snapshot(self) -> JsonSnapshot:
        return JsonSnapshot(
            {
                "recommendation_id": str(self.recommendation_id),
                "recommendation_version": self.recommendation_version,
                "recommendation_status": self.recommendation_status,
                "suppression_block_id": str(self.suppression_block_id),
                "resolved_at": self.resolved_at.isoformat(),
                "reason": self.reason,
                "remaining_blockers": list(self.remaining_blockers),
            }
        )

    @classmethod
    def from_snapshot(
        cls, snapshot: JsonSnapshot
    ) -> MarkRecommendationNotRelevantResponse:
        value = snapshot.to_json_object()
        return cls(
            UUID(value["recommendation_id"]),
            value["recommendation_version"],
            value["recommendation_status"],
            UUID(value["suppression_block_id"]),
            datetime.fromisoformat(value["resolved_at"]),
            value["reason"],
            tuple(value["remaining_blockers"]),
        )
