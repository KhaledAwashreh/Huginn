from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class SignalWindow:
    cutoff: datetime
    as_of: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.cutoff, datetime) or not isinstance(
            self.as_of, datetime
        ):
            raise ValueError("signal window bounds must be datetimes")
        if not _aware(self.cutoff) or not _aware(self.as_of):
            raise ValueError("signal window bounds must be timezone-aware")
        cutoff = self.cutoff.astimezone(UTC)
        as_of = self.as_of.astimezone(UTC)
        if cutoff > as_of:
            raise ValueError("cutoff must not be after as_of")
        object.__setattr__(self, "cutoff", cutoff)
        object.__setattr__(self, "as_of", as_of)


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None
