"""Immutable input and output records for attribute assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

type AttributeValue = tuple[str | None, ...] | str | None


@dataclass(frozen=True)
class CompanyAttributes:
    company_id: UUID
    business_sector: tuple[str | None, ...] | None
    company_scale: str | None
    country: str | None


@dataclass(frozen=True)
class SourceFact:
    company_id: UUID
    source: str
    stable_id: str
    observation_id: UUID
    snapshot_id: UUID
    raw_token: str | None
    resolution_token: str
    context_version: str
    policy_version: str
    occurred_at: datetime | None
    source_fields: str


@dataclass(frozen=True)
class FieldProposal:
    company_id: UUID
    field_name: str
    old_value: AttributeValue
    proposed_value: AttributeValue
    status: str
    reason: str
    source_fields: tuple[str, ...]
    supporting_fact_ids: tuple[UUID, ...]
    mapping_version: str
