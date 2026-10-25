"""Deterministic field mapping and conservative fill-missing reduction."""

from __future__ import annotations

import json
from collections.abc import Iterable

from huginn.elt.gold.models.attribute_value import AttributeValue
from huginn.elt.gold.models.company_attributes import CompanyAttributes
from huginn.elt.gold.models.field_proposal import FieldProposal
from huginn.elt.gold.models.source_fact import SourceFact
from huginn.elt.gold.policies.company_scale import team_size_to_scale
from huginn.elt.gold.policies.country_labels import (
    EU_CATEGORY_COUNTRY_LABELS,
    EU_PLACE_COUNTRY_LABELS,
    YC_COUNTRY_LABELS,
    country_identity,
)

MAPPING_VERSION = "attribute-mapping-v1"
_FIELDS = ("business_sector", "company_scale", "country")


def _size_value(raw: str | None) -> tuple[str, str | None]:
    if raw is None:
        return "absent", None
    try:
        value = json.loads(raw)
    except TypeError, ValueError:
        return "invalid", None
    if value is None:
        return "absent", None
    scale = team_size_to_scale(value)
    if scale is None:
        return "invalid", None
    return "valid", scale


def _industries(raw: str | None) -> tuple[str, tuple[str, ...] | None]:
    if raw is None:
        return "absent", None
    try:
        value = json.loads(raw)
    except TypeError, ValueError:
        return "invalid", None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return "invalid", None
    labels = tuple(
        sorted(
            {
                item.strip()
                for item in value
                if item.strip() and item.strip().casefold() != "unspecified"
            }
        )
    )
    return ("valid", labels) if labels else ("absent", None)


def _raw_value(fact: SourceFact, key: str) -> tuple[str, str | None]:
    try:
        fields = json.loads(fact.source_fields)
    except TypeError, ValueError:
        return "invalid", None
    if not isinstance(fields, dict):
        return "invalid", None
    if key not in fields:
        return "absent", None
    value = fields.get(key)
    if value is None:
        return "absent", None
    if key == "industries" and not isinstance(value, list):
        return "invalid", None
    return "present", json.dumps(value)


def _field_candidate(
    fact: SourceFact,
    field_name: str,
    yc_country_labels: frozenset[str] | None = None,
) -> tuple[str, AttributeValue, str | None]:
    if field_name == "business_sector":
        if fact.source != "yc":
            return "unsupported", None, None
        raw_status, raw = _raw_value(fact, "industries")
        if raw_status in {"absent", "invalid"}:
            return raw_status, None, "yc.industries"
        status, value = _industries(raw)
        return status, value, "yc.industries"
    if field_name == "company_scale":
        if fact.source != "yc":
            return "unsupported", None, None
        raw_status, raw = _raw_value(fact, "team_size")
        if raw_status in {"absent", "invalid"}:
            return raw_status, None, "yc.team_size"
        status, value = _size_value(raw)
        return status, value, "yc.team_size"
    if field_name == "country":
        return _country_candidate(fact, yc_country_labels)
    return "unsupported", None, None


def _country_candidate(
    fact: SourceFact, yc_country_labels: frozenset[str] | None = None
) -> tuple[str, AttributeValue, str | None]:
    if fact.source == "yc":
        field_status, encoded = _raw_value(fact, "all_locations")
        if field_status in {"absent", "invalid"}:
            return field_status, None, "yc.all_locations"
        assert encoded is not None
        raw = json.loads(encoded)
        if not isinstance(raw, str):
            return "invalid", None, "yc.all_locations"
        if not raw.strip():
            return "absent", None, "yc.all_locations"
        segments = raw.split(";")
        if len(segments) != 1:
            return "ambiguous", None, "yc.all_locations"
        components = [part.strip() for part in segments[0].split(",")]
        if (
            len(components) < 2
            or any(not component for component in components)
            or "remote" in raw.casefold()
        ):
            return "ambiguous", None, "yc.all_locations"
        label = components[-1]
        if label == "Georgia" or label not in (
            YC_COUNTRY_LABELS if yc_country_labels is None else yc_country_labels
        ):
            return "ambiguous", None, "yc.all_locations"
        return "valid", label, "yc.all_locations"

    if fact.source in {"eu", "eu_startups", "eu-startups"}:
        category_status, category_raw = _raw_value(fact, "category")
        place_status, place_raw = _raw_value(fact, "place")
        fields = "eu_startups.category|eu_startups.place"
        if "invalid" in {category_status, place_status}:
            return "invalid", None, fields
        if "absent" in {category_status, place_status}:
            return "absent", None, fields
        assert category_raw is not None and place_raw is not None
        category = json.loads(category_raw)
        place = json.loads(place_raw)
        if not isinstance(category, str) or not isinstance(place, str):
            return "invalid", None, fields
        if category not in EU_CATEGORY_COUNTRY_LABELS:
            return "ambiguous", None, fields
        place_parts = place.split(",")
        place_label = place if len(place_parts) == 1 else place_parts[-1].strip()
        if place_label not in EU_PLACE_COUNTRY_LABELS:
            return "ambiguous", None, fields
        if country_identity(category) != country_identity(place_label):
            return "conflict", None, fields
        return "valid", category, fields

    return "unsupported", None, None


def _proposal(
    company: CompanyAttributes,
    field_name: str,
    facts: list[SourceFact],
    yc_country_labels: frozenset[str] | None = None,
) -> FieldProposal:
    old_value: AttributeValue = getattr(company, field_name)
    candidates = [
        (_field_candidate(fact, field_name, yc_country_labels), fact) for fact in facts
    ]
    usable = [(value, fact) for value, fact in candidates if value[0] == "valid"]
    blockers = [
        (value, fact)
        for value, fact in candidates
        if value[0] in {"invalid", "ambiguous", "conflict"}
    ]
    supported = [
        (value, fact) for value, fact in candidates if value[0] != "unsupported"
    ]
    status, proposed, reason = "absent", None, "No supported source value is present."
    lineage: list[SourceFact] = []
    fields: set[str] = set()

    existing = _is_meaningful(field_name, old_value)
    if existing:
        evidence = usable + blockers
        if evidence:
            lineage = [fact for _, fact in evidence]
            source_values = {value[1] for value, _ in usable}
            identities = {_canonical(field_name, value) for value in source_values}
            if (
                any(candidate[0] == "conflict" for candidate, _ in blockers)
                or len(identities) > 1
                or any(
                    _canonical(field_name, value) != _canonical(field_name, old_value)
                    for value in source_values
                )
            ):
                status, reason = (
                    "conflict",
                    "Current evidence disagrees with the existing Gold value.",
                )
            elif blockers:
                status = (
                    "invalid"
                    if any(candidate[0] == "invalid" for candidate, _ in blockers)
                    else "ambiguous"
                )
                reason = "Current evidence cannot validate the existing Gold value; it is preserved."
            else:
                status, proposed, reason = (
                    "unchanged",
                    old_value,
                    "Current evidence agrees with the existing Gold value.",
                )
        else:
            status, proposed, reason = (
                "unchanged",
                old_value,
                "Existing value is preserved; policy only fills missing values.",
            )
    elif blockers:
        blocker_statuses = {outcome[0] for outcome, _ in blockers}
        status = (
            "conflict"
            if "conflict" in blocker_statuses
            else "invalid"
            if "invalid" in blocker_statuses
            else "ambiguous"
        )
        reason = {
            "conflict": "Current explicit evidence conflicts.",
            "invalid": "Invalid supported evidence prevents a fill.",
            "ambiguous": "Ambiguous supported evidence prevents a fill.",
        }[status]
        lineage = [
            fact
            for outcome, fact in supported
            if outcome[0] in {"invalid", "ambiguous", "conflict", "valid"}
        ]
    elif usable:
        values = {value[1] for value, _ in usable}
        identities = {_canonical(field_name, value) for value in values}
        lineage = [fact for _, fact in usable]
        if len(identities) > 1:
            status, reason = "conflict", "Current supported facts disagree."
        else:
            proposed = usable[0][0][1]
            status, reason = (
                "proposed",
                "Current supported source evidence maps to this value.",
            )
    elif supported:
        status, reason = "absent", "Supported source evidence has no meaningful value."
        lineage = [fact for value, fact in supported if value[0] == "absent"]
    else:
        status, reason = (
            "unsupported",
            "Available sources have no approved mapping for this field.",
        )
        lineage = facts

    for fact in lineage:
        candidate = _field_candidate(fact, field_name, yc_country_labels)
        if candidate[2]:
            fields.update(candidate[2].split("|"))
    return FieldProposal(
        company_id=company.company_id,
        field_name=field_name,
        old_value=old_value,
        proposed_value=proposed,
        status=status,
        reason=reason,
        source_fields=tuple(sorted(fields)),
        supporting_fact_ids=tuple(
            sorted({fact.observation_id for fact in lineage}, key=str)
        ),
        mapping_version=MAPPING_VERSION,
    )


def _is_meaningful(field_name: str, value: AttributeValue) -> bool:
    if value is None:
        return False
    if field_name == "business_sector":
        return isinstance(value, tuple) and any(
            item is not None
            and item.strip(" ")
            and item.strip(" ").casefold() != "unspecified"
            for item in value
        )
    if isinstance(value, str):
        return bool(value.strip(" "))
    return True


def _canonical(field_name: str, value: AttributeValue) -> object:
    if field_name == "business_sector" and isinstance(value, tuple):
        return frozenset(
            item.strip(" ").lower()
            for item in value
            if item is not None
            and item.strip(" ")
            and item.strip(" ").casefold() != "unspecified"
        )
    if field_name == "country" and isinstance(value, str):
        return value.strip(" ").lower()
    return value


def assess(
    company: CompanyAttributes,
    facts: Iterable[SourceFact],
    *,
    yc_country_labels: frozenset[str] | None = None,
) -> tuple[FieldProposal, ...]:
    """Assess all three matching attributes without mutation or inference."""
    matching = sorted(
        (fact for fact in facts if fact.company_id == company.company_id),
        key=lambda fact: (
            fact.source,
            fact.stable_id,
            str(fact.observation_id),
            str(fact.snapshot_id),
        ),
    )
    return tuple(
        _proposal(company, field_name, matching, yc_country_labels)
        for field_name in _FIELDS
    )
