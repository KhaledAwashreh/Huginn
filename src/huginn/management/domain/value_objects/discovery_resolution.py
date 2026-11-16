from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DiscoveryResolution:
    value: Literal["save", "not_relevant", "later", "none"]

    def __post_init__(self) -> None:
        if self.value not in {"save", "not_relevant", "later", "none"}:
            raise ValueError("invalid discovery resolution")
