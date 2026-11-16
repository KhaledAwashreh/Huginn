"""Validate recommendation input choices before invoking shared fit policy."""

from huginn.management.application.policies.icp_selection import validate_icp_selection
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.matchmaking.domain.policies.business_company_fit import normalize_country


def validate_exclusions(exclusions):
    for item in exclusions:
        if item.get("kind") == "geography":
            geo = item.get("geography", {})
            if (
                geo.get("kind") != "country"
                or normalize_country(geo.get("value")) is None
            ):
                raise ValidationDomainError(
                    "Choose explicit country exclusions before generating research recommendations"
                )
        elif item.get("kind") not in {"company", "industry"}:
            raise ValidationDomainError("Unsupported research exclusion")


def validate_icp_filters(icp: dict) -> None:
    validate_icp_selection(
        icp.get("industries", []), icp.get("geographies", []), icp.get("exclusions", [])
    )
    for geo in icp.get("geographies", []):
        if geo.get("kind") != "country" or normalize_country(geo.get("value")) is None:
            raise ValidationDomainError(
                "Choose recognized countries for ICP geography filters"
            )
