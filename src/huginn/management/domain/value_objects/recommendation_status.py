from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RecommendationStatus:
    value: Literal["open", "converted", "rejected"]

    def __post_init__(self) -> None:
        if self.value not in {"open", "converted", "rejected"}:
            raise ValueError("invalid recommendation status")
