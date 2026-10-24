"""Pure validation and canonical fingerprint rules for source context."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.types.source_context import OutcomeStatus, SourceName


def canonical_payload_sha256(payload: Mapping[str, object]) -> str:
    """Hash full payload JSON, independent of mapping insertion order."""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_record(
    source: SourceName, stable_id: str, extraction: SourceExtraction
) -> tuple[OutcomeStatus, str | None]:
    if extraction.source != source:
        return "failed", "normalized source does not match run source"
    if extraction.stable_id is not None and extraction.stable_id != stable_id:
        return "failed", "normalized stable ID does not match Bronze stable ID"
    if extraction.status == "captured":
        if extraction.stable_id != stable_id:
            return "failed", "normalized stable ID does not match Bronze stable ID"
        if (
            (
                extraction.normalized_text is None
                or not extraction.normalized_text.strip()
            )
            and not extraction.source_fields
            and not extraction.source_times
        ):
            return "failed", "captured extraction has no text or source observations"
    return extraction.status, extraction.reason
