from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from huginn.elt.gold.models.attribute_value import AttributeValue


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
