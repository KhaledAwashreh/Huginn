"""Pure normalization of YC directory records for source-context capture."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime

from huginn.elt.silver.models.source_extraction import SourceExtraction

_SOURCE_FIELDS = (
    "name",
    "slug",
    "website",
    "one_liner",
    "long_description",
    "tags",
    "tags_highlighted",
    "regions",
    "industries",
    "former_names",
    "industry",
    "subindustry",
    "team_size",
    "location",
    "all_locations",
    "batch",
    "stage",
    "status",
    "isHiring",
)
_TEXT_FIELDS = (
    "name",
    "slug",
    "website",
    "one_liner",
    "long_description",
    "location",
    "all_locations",
    "batch",
    "stage",
    "status",
    "industry",
    "subindustry",
)
_LIST_FIELDS = ("tags", "tags_highlighted", "regions", "industries", "former_names")


def _failed(reason: str, stable_id: str | None = None) -> SourceExtraction:
    return SourceExtraction(
        source="yc", stable_id=stable_id, status="failed", reason=reason
    )


def normalize_yc(payload: dict[str, object]) -> SourceExtraction:
    """Return source-faithful YC context without applying staging eligibility.

    YC's legacy staging parser filters inactive/acquired companies, but these
    records remain valid observations here. Optional fields are copied only
    when present, preserving the difference between absent, explicit null,
    false, and zero. Supplied values are type-checked rather than coerced.
    """
    if not isinstance(payload, Mapping):
        return _failed("payload must be an object")

    raw_id = payload.get("id")
    if (
        isinstance(raw_id, bool)
        or not isinstance(raw_id, (str, int))
        or not str(raw_id)
    ):
        return _failed("missing or invalid id")
    stable_id = str(raw_id)

    slug = payload.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        return _failed("missing or invalid slug", stable_id)

    for field in _TEXT_FIELDS:
        if (
            field in payload
            and payload[field] is not None
            and not isinstance(payload[field], str)
        ):
            return _failed(f"{field} must be a string or null", stable_id)
    for field in _LIST_FIELDS:
        if field in payload and payload[field] is not None:
            values = payload[field]
            if not isinstance(values, list) or any(
                not isinstance(item, str) for item in values
            ):
                return _failed(f"{field} must be a list of strings or null", stable_id)
    if (
        "isHiring" in payload
        and payload["isHiring"] is not None
        and not isinstance(payload["isHiring"], bool)
    ):
        return _failed("isHiring must be a boolean or null", stable_id)
    if "team_size" in payload and payload["team_size"] is not None:
        team_size = payload["team_size"]
        if isinstance(team_size, bool) or not isinstance(team_size, int):
            return _failed("team_size must be an integer or null", stable_id)
    if "launched_at" in payload and payload["launched_at"] is not None:
        launched_at = payload["launched_at"]
        if isinstance(launched_at, bool) or not isinstance(launched_at, (int, float)):
            return _failed("launched_at must be numeric or null", stable_id)
        try:
            if not math.isfinite(launched_at):
                raise ValueError
            datetime.fromtimestamp(launched_at, tz=UTC)
        except OverflowError, OSError, ValueError:
            return _failed(
                "launched_at must be a finite, representable timestamp or null",
                stable_id,
            )

    fields = {key: payload[key] for key in _SOURCE_FIELDS if key in payload}
    text_values = [payload.get(key) for key in ("one_liner", "long_description")]
    present_text = [value for value in text_values if isinstance(value, str)]
    nonempty_text = [value for value in present_text if value]
    normalized_text = (
        "\n\n".join(nonempty_text) if nonempty_text else ("" if present_text else None)
    )
    source_times = (
        {"launched_at": payload["launched_at"]} if "launched_at" in payload else {}
    )

    return SourceExtraction(
        source="yc",
        stable_id=stable_id,
        status="captured",
        source_url=f"https://www.ycombinator.com/companies/{slug}",
        normalized_text=normalized_text,
        source_fields=fields,
        source_times=source_times,
    )
