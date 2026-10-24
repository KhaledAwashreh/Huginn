from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from huginn.elt.silver.models.bronze_input import BronzeInput
from huginn.elt.silver.models.context_run import ContextRun
from huginn.elt.silver.models.persist_run_result import PersistRunResult
from huginn.elt.silver.models.source_context_audit_snapshot import (
    AuditSnapshot as SourceContextAuditSnapshot,
)
from huginn.elt.silver.types.source_context import SourceName


class InputsRepository(Protocol):
    def read_inputs(
        self, source: SourceName, limit: int | None = None, *, read_only: bool = True
    ) -> list[BronzeInput]: ...
    def count_inputs(self, source: SourceName) -> int: ...
    def coverage_counts(self, source: SourceName) -> dict[str, int]: ...
    def read_audit_snapshot(
        self, source: SourceName, limit: int | None = None
    ) -> SourceContextAuditSnapshot: ...
    def persist_run(self, run: ContextRun) -> PersistRunResult: ...


class AuditSnapshotProtocol(Protocol):
    inputs: Sequence[BronzeInput]
    available_count: int
    coverage_counts: dict[str, int]
    downstream_by_stable_id: Mapping[str, Mapping[str, object]]
