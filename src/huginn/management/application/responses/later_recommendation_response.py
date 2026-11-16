"""Committed Later duration, replacement and remaining blockers."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True, slots=True)
class LaterRecommendationResponse:
    recommendation_id: UUID
    recommendation_version: int
    suppression_block_id: UUID
    replaced_pause_id: UUID | None
    pause_choice: str
    repeat_interval_days: int
    preference_updated_at: datetime
    selected_at: datetime
    expires_at: datetime | None
    remaining_blockers: tuple[str, ...]

    def snapshot(self) -> JsonSnapshot:
        return JsonSnapshot(
            {
                "recommendation_id": str(self.recommendation_id),
                "recommendation_version": self.recommendation_version,
                "suppression_block_id": str(self.suppression_block_id),
                "replaced_pause_id": str(self.replaced_pause_id)
                if self.replaced_pause_id
                else None,
                "pause_choice": self.pause_choice,
                "repeat_interval_days": self.repeat_interval_days,
                "preference_updated_at": self.preference_updated_at.isoformat(),
                "selected_at": self.selected_at.isoformat(),
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                "remaining_blockers": list(self.remaining_blockers),
            }
        )

    @classmethod
    def from_snapshot(cls, snapshot: JsonSnapshot) -> LaterRecommendationResponse:
        value = snapshot.to_json_object()
        return cls(
            UUID(value["recommendation_id"]),
            value["recommendation_version"],
            UUID(value["suppression_block_id"]),
            UUID(value["replaced_pause_id"]) if value["replaced_pause_id"] else None,
            value["pause_choice"],
            value["repeat_interval_days"],
            datetime.fromisoformat(value["preference_updated_at"]),
            datetime.fromisoformat(value["selected_at"]),
            datetime.fromisoformat(value["expires_at"])
            if value["expires_at"]
            else None,
            tuple(value["remaining_blockers"]),
        )
