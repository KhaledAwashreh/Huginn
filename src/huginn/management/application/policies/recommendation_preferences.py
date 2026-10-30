"""Compare explicit preferences without interpreting unknowns as exclusions."""

from huginn.management.application.policies.country_identity import normalize_country
from huginn.management.application.policies.icp_selection import validate_icp_selection
from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.domain.errors.errors import ValidationDomainError


def preference_status(actual, items, key):
    wanted = {str(item[key]).strip().casefold() for item in items if key in item}
    values = (actual,) if isinstance(actual, str) else actual or ()
    known = {
        str(value).strip().casefold()
        for value in values
        if value and str(value).strip().casefold() not in {"unknown", "unspecified"}
    }
    if not wanted or not known:
        return "unknown"
    return "match" if wanted & known else "mismatch"


def country_preference(actual, geographies):
    countries = [
        normalize_country(geo.get("value"))
        for geo in geographies
        if geo.get("kind") == "country"
    ]
    wanted = {country for country in countries if country is not None}
    known = normalize_country(actual)
    if not wanted or known is None:
        return "unknown"
    if known in wanted:
        return "match"
    if any(geo.get("kind") == "region" for geo in geographies) or None in countries:
        return "unknown"
    return "mismatch"


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


def icp_fit(company: RecommendationCompany, icp: dict) -> dict[str, str]:
    """OR within dimensions; every known populated dimension must agree."""
    statuses = {
        "industry": preference_status(
            company.business_sector, icp.get("industries", []), "name"
        ),
        "size": preference_status(
            company.company_scale, icp.get("company_sizes", []), "band"
        ),
        "country": country_preference(company.country, icp.get("geographies", [])),
    }
    configured = {
        "industry": "industries",
        "size": "company_sizes",
        "country": "geographies",
    }
    return {
        field: status
        for field, status in statuses.items()
        if icp.get(configured[field])
    }


def excluded_from_research(company: RecommendationCompany, exclusions):
    validate_exclusions(exclusions)
    for item in exclusions:
        kind = item.get("kind")
        if kind == "company" and str(company.company_id) == item.get("company_id"):
            return True
        if (
            kind == "industry"
            and preference_status(company.business_sector, [item], "name") == "match"
        ):
            return True
        if (
            kind == "geography"
            and country_preference(company.country, [item["geography"]]) == "match"
        ):
            return True
    return False
