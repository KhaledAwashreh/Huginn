"""Read-only assessment repository contract and immutable source snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from huginn.elt.gold.attribute_promotion.models import CompanyAttributes, SourceFact
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow


@dataclass(frozen=True)
class AssessmentSnapshot:
    companies: tuple[CompanyAttributes, ...]
    facts: tuple[SourceFact, ...]
    scope: str


class AttributeAssessmentRepository(Protocol):
    def read_snapshot(self, limit: int | None = None) -> AssessmentSnapshot: ...

    def candidate_ids(
        self,
        snapshot: AssessmentSnapshot,
        companies: tuple[CompanyAttributes, ...],
        criteria: CompiledCriteria,
        window: SignalWindow,
    ) -> tuple[UUID, ...]: ...
