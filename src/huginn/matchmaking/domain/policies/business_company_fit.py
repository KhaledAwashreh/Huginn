"""Shared ICP fit and exclusion semantics; no scoring weights are applied here."""

from collections.abc import Mapping, Sequence
from uuid import UUID

import pycountry

from huginn.matchmaking.domain.value_objects.company_fit_assessment import (
    CompanyFitAssessment,
)


def normalize_country(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = {"uk": "GB", "united states of america": "US"}.get(
        value.strip().casefold(), value.strip()
    )
    try:
        return pycountry.countries.lookup(normalized).alpha_2
    except LookupError:
        return None


def preference_status(
    actual: str | Sequence[str] | None,
    items: Sequence[Mapping[str, object]],
    key: str,
) -> str:
    wanted = {
        str(item[key]).strip().casefold()
        for item in items
        if key in item and str(item[key]).strip()
    }
    values = (actual,) if isinstance(actual, str) else actual or ()
    known = {
        value.strip().casefold()
        for value in values
        if isinstance(value, str)
        and value.strip()
        and value.strip().casefold() not in {"unknown", "unspecified"}
    }
    if not wanted or not known:
        return "unknown"
    return "match" if wanted & known else "mismatch"


def country_preference(
    actual: object, geographies: Sequence[Mapping[str, object]]
) -> str:
    countries = tuple(
        normalize_country(geo.get("value"))
        for geo in geographies
        if geo.get("kind") == "country"
    )
    wanted = {country for country in countries if country is not None}
    known = normalize_country(actual)
    if not wanted or known is None:
        return "unknown"
    if known in wanted:
        return "match"
    if any(geo.get("kind") == "region" for geo in geographies) or None in countries:
        return "unknown"
    return "mismatch"


def is_explicitly_excluded(
    company_id: UUID | str,
    industries: Sequence[str] | None,
    country: object,
    exclusions: Sequence[Mapping[str, object]],
) -> bool:
    for exclusion in exclusions:
        kind = exclusion.get("kind")
        if kind == "company" and str(company_id) == str(exclusion.get("company_id")):
            return True
        if (
            kind == "industry"
            and preference_status(industries, (exclusion,), "name") == "match"
        ):
            return True
        if kind == "geography":
            geography = exclusion.get("geography")
            if (
                isinstance(geography, Mapping)
                and country_preference(country, (geography,)) == "match"
            ):
                return True
    return False


def assess_company_fit(
    company_id: UUID | str,
    industries: Sequence[str] | None,
    company_size: str | None,
    country: object,
    icp: Mapping[str, object],
) -> CompanyFitAssessment:
    dimensions: dict[str, str] = {}
    if icp.get("industries"):
        dimensions["industry"] = preference_status(
            industries,
            icp["industries"],
            "name",  # type: ignore[arg-type]
        )
    if icp.get("company_sizes"):
        dimensions["size"] = preference_status(
            company_size,
            icp["company_sizes"],
            "band",  # type: ignore[arg-type]
        )
    if icp.get("geographies"):
        dimensions["country"] = country_preference(
            country,
            icp["geographies"],  # type: ignore[arg-type]
        )
    exclusions = icp.get("exclusions", ())
    excluded = is_explicitly_excluded(
        company_id,
        industries,
        country,
        exclusions if isinstance(exclusions, Sequence) else (),  # type: ignore[arg-type]
    )
    return CompanyFitAssessment(dimensions, excluded)
