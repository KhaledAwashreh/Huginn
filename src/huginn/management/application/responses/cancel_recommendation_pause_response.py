"""Committed result of cancelling a pause block."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True, slots=True)
class CancelRecommendationPauseResponse:
    suppression_block_id: UUID
    block_version: int
    cleared_at: datetime
    remaining_blockers: tuple[str, ...]

    def snapshot(self) -> JsonSnapshot:
        return JsonSnapshot(
            {
                "suppression_block_id": str(self.suppression_block_id),
                "block_version": self.block_version,
                "cleared_at": self.cleared_at.isoformat(),
                "remaining_blockers": list(self.remaining_blockers),
            }
        )

    @classmethod
    def from_snapshot(cls, snapshot: JsonSnapshot) -> CancelRecommendationPauseResponse:
        value = snapshot.to_json_object()
        return cls(
            UUID(value["suppression_block_id"]),
            value["block_version"],
            datetime.fromisoformat(value["cleared_at"]),
            tuple(value["remaining_blockers"]),
        )
