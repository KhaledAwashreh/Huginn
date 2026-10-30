"""Reject contradictory selected and excluded ICP values before commit."""

from huginn.management.application.policies.country_identity import normalize_country
from huginn.management.domain.errors.errors import ValidationDomainError


def _geography_key(geo):
    value = str(geo.get("value", "")).strip().casefold()
    return geo.get("kind"), (normalize_country(value) or value) if geo.get(
        "kind"
    ) == "country" else value


def validate_icp_selection(industries, geographies, exclusions):
    selected_industries = {
        str(item.get("name", "")).strip().casefold() for item in industries
    }
    selected_geographies = {_geography_key(item) for item in geographies}
    conflicts = []
    for item in exclusions:
        if (
            item.get("kind") == "industry"
            and str(item.get("name", "")).strip().casefold() in selected_industries
        ):
            conflicts.append(str(item["name"]).strip())
        elif (
            item.get("kind") == "geography"
            and _geography_key(item.get("geography", {})) in selected_geographies
        ):
            conflicts.append(str(item["geography"]["value"]).strip())
    if conflicts:
        raise ValidationDomainError(
            "ICP values cannot be both selected and excluded: "
            + ", ".join(sorted(set(conflicts)))
            + ". Remove each conflict from one list."
        )
