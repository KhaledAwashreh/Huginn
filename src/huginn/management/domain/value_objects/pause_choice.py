import re
from dataclasses import dataclass

_DAY_MUTE = re.compile(r"^d(?:[1-9]|[1-9][0-9]|[12][0-9]{2}|3[0-5][0-9]|36[0-5])$")


@dataclass(frozen=True)
class PauseChoice:
    value: str

    def __post_init__(self) -> None:
        if self.value in {"x1", "x2", "x3", "x4", "indefinite"}:
            return
        if _DAY_MUTE.fullmatch(self.value):
            return
        raise ValueError("invalid pause choice")

    @property
    def days(self) -> int | None:
        if self.value.startswith("d"):
            return int(self.value[1:])
        return None
