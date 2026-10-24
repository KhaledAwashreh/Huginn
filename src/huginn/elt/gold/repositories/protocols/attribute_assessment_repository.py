"""Read-only assessment repository contract and immutable source snapshot."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from huginn.elt.gold.models.assessment_snapshot import AssessmentSnapshot
from huginn.elt.gold.models.company_attributes import CompanyAttributes
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow


class AttributeAssessmentRepository(Protocol):
    def read_snapshot(self, limit: int | None = None) -> AssessmentSnapshot: ...

    def candidate_ids(
        self,
        snapshot: AssessmentSnapshot,
        companies: tuple[CompanyAttributes, ...],
        criteria: CompiledCriteria,
        window: SignalWindow,
    ) -> tuple[UUID, ...]: ...
