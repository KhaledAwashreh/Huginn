"""Pure values shared by source context normalizers and persistence."""

from __future__ import annotations

from dataclasses import dataclass, field

from huginn.elt.silver.types.source_context import OutcomeStatus, SourceName


@dataclass(frozen=True)
class SourceExtraction:
    source: SourceName
    stable_id: str | None
    status: OutcomeStatus
    reason: str | None = None
    source_url: str | None = None
    normalized_text: str | None = None
    header_span: tuple[int, int] | None = None
    body_span: tuple[int, int] | None = None
    source_fields: dict[str, object] = field(default_factory=dict)
    source_times: dict[str, object] = field(default_factory=dict)
