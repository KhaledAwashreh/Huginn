from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OfferCycleStatus:
    value: Literal["preparing", "sending", "confirmed", "abandoned", "unknown"]

    def __post_init__(self) -> None:
        if self.value not in {
            "preparing",
            "sending",
            "confirmed",
            "abandoned",
            "unknown",
        }:
            raise ValueError("invalid offer cycle status")
