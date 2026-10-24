"""Reconciliation boundary; see docs/source-currentness.md."""

from __future__ import annotations

from typing import Protocol

from huginn.elt.silver.models.lifecycle_facts import LifecycleFacts
from huginn.elt.silver.models.lifecycle_input import LifecycleInput
from huginn.elt.silver.models.reconcile_result import ReconcileResult
from huginn.elt.silver.types.source_context import SourceName


class LifecycleRepository(Protocol):
    def read_inputs(
        self, source: SourceName, limit: int | None = None
    ) -> tuple[LifecycleInput, ...]: ...

    def reconcile(
        self, item: LifecycleInput, facts: LifecycleFacts
    ) -> ReconcileResult: ...
