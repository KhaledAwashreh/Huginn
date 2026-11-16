from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SuppressionKind:
    value: Literal["cooldown", "pause", "rejection"]

    def __post_init__(self) -> None:
        if self.value not in {
            "cooldown",
            "pause",
            "rejection",
        }:
            raise ValueError("invalid suppression kind")
