"""Match workflow vocabulary exposed by management; architecture.md section 4.4."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class MatchStatus:
    value: Literal["new", "contacted", "responded", "dismissed", "converted"]

    def __post_init__(self) -> None:
        if self.value not in {
            "new",
            "contacted",
            "responded",
            "dismissed",
            "converted",
        }:
            raise ValueError("invalid match status")


__all__ = ["MatchStatus"]
