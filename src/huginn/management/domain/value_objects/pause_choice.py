from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PauseChoice:
    value: Literal["x1", "x2", "x3", "x4", "indefinite"]

    def __post_init__(self) -> None:
        if self.value not in {"x1", "x2", "x3", "x4", "indefinite"}:
            raise ValueError("invalid pause choice")
