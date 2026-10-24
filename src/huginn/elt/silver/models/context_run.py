from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from huginn.elt.silver.models.context_record import ContextRecord
from huginn.elt.silver.types.source_context import SourceName


@dataclass(frozen=True)
class ContextRun:
    source: SourceName
    parser_version: str
    input_fingerprint: str
    records: tuple[ContextRecord, ...]
    mode: Literal["capture"] = "capture"
    metadata: dict[str, object] = field(default_factory=dict)
