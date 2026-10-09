"""Account authorization role values."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class AccountRole:
    value: Literal["user", "admin"]

    def __post_init__(self) -> None:
        if self.value not in {"user", "admin"}:
            raise ValueError("invalid account role")
