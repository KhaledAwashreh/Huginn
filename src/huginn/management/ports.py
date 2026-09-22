"""Management runtime ports defined by ADR-0011."""

from typing import Protocol


class ReadinessPort(Protocol):
    """Readiness boundary defined by ADR-0011."""

    def is_ready(self) -> bool: ...
