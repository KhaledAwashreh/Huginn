from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True)
class StrategyAssessmentSnapshot:
    strategy_id: UUID
    offering_id: UUID
    ideal_client_profile_id: UUID
    strategy_snapshot: JsonSnapshot
    offering_snapshot: JsonSnapshot
    ideal_client_profile_snapshot: JsonSnapshot
    assessment_snapshot: JsonSnapshot

    def __post_init__(self) -> None:
        for name in ("strategy_id", "offering_id", "ideal_client_profile_id"):
            if not isinstance(getattr(self, name), UUID):
                raise ValueError(f"{name} must be a UUID")
        for name in (
            "strategy_snapshot",
            "offering_snapshot",
            "ideal_client_profile_snapshot",
            "assessment_snapshot",
        ):
            value = getattr(self, name)
            if not isinstance(value, JsonSnapshot):
                object.__setattr__(self, name, JsonSnapshot(value))
