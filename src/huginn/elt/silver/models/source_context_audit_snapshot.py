from __future__ import annotations

from dataclasses import dataclass

from huginn.elt.silver.models.bronze_input import BronzeInput


@dataclass(frozen=True)
class AuditSnapshot:
    inputs: tuple[BronzeInput, ...]
    available_count: int
    coverage_counts: dict[str, int]
    downstream_by_stable_id: dict[str, dict[str, object]]
