from __future__ import annotations

from dataclasses import dataclass, field

from huginn.elt.silver.models.source_extraction import SourceExtraction


@dataclass(frozen=True)
class ContextRecord:
    stable_id: str
    payload: dict[str, object]
    extraction: SourceExtraction
    observation: dict[str, object] = field(default_factory=dict)
