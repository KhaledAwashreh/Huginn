"""Reconciliation boundary; see docs/source-currentness.md."""

from __future__ import annotations

from typing import Protocol

from huginn.elt.silver.context.models import SourceName
from huginn.elt.silver.currentness.models import (
    LifecycleFacts,
    LifecycleInput,
    ReconcileResult,
)


class LifecycleRepository(Protocol):
    def read_inputs(
        self, source: SourceName, limit: int | None = None
    ) -> tuple[LifecycleInput, ...]: ...

    def reconcile(
        self, item: LifecycleInput, facts: LifecycleFacts
    ) -> ReconcileResult: ...
