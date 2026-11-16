from dataclasses import dataclass
from datetime import datetime

from huginn.matchmaking.domain.value_objects._ranking_validation import aware


@dataclass(frozen=True)
class BusinessCompanyState:
    """Current suppression projection; delivery flags derive from OfferCycle state."""

    first_presented_at: datetime | None = None
    cooldown_until: datetime | None = None
    paused_until: datetime | None = None
    paused_indefinitely: bool = False
    rejected: bool = False
    has_relationship: bool = False
    pending_delivery: bool = False
    uncertain_delivery: bool = False

    def __post_init__(self) -> None:
        for name in ("first_presented_at", "cooldown_until", "paused_until"):
            value = getattr(self, name)
            if value is not None:
                aware(value, name)
        for name in (
            "paused_indefinitely",
            "rejected",
            "has_relationship",
            "pending_delivery",
            "uncertain_delivery",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
