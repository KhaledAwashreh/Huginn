from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.types.source_lifecycle import (
    HiringState,
    IdentityState,
    ListingState,
)


@dataclass(frozen=True)
class LifecycleFacts:
    listing_state: ListingState
    hiring_state: HiringState
    identity_state: IdentityState
    reason: str
    explicit_domain: str | None
    occurred_at: datetime | None
    context: SourceExtraction
