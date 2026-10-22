"""Immutable reconciliation values; see docs/source-currentness.md."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.elt.silver.context.models import SourceExtraction, SourceName

POLICY_VERSION = "source-lifecycle-v1"

ListingState = Literal["available", "withdrawn", "invalid", "unknown"]
HiringState = Literal["true", "false", "unknown", "not_applicable"]
IdentityState = Literal["consistent", "unresolved", "mismatch", "missing"]


@dataclass(frozen=True)
class LifecycleInput:
    source: SourceName
    stable_id: str
    payload: dict[str, object]
    raw_token: str
    resolution_token: str
    resolved_company_key: str | None
    key_derivation: str | None
    company_id: UUID | None
    fetched_at: datetime
    last_checked_at: datetime


@dataclass(frozen=True)
class LifecycleFacts:
    listing_state: ListingState
    hiring_state: HiringState
    identity_state: IdentityState
    reason: str
    explicit_domain: str | None
    occurred_at: datetime | None
    context: SourceExtraction


@dataclass(frozen=True)
class ReconcileResult:
    status: Literal["created", "unchanged", "stale"]
    observation_id: UUID | None
