"""Pure comparison policy for missing-field and country-alias counterfactuals."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace

from huginn.elt.gold.models.company_attributes import CompanyAttributes
from huginn.elt.gold.models.source_fact import SourceFact
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow

ATTRIBUTE_FIELDS = ("business_sector", "company_scale", "country")
# Explicit, experimental aliases; never applied by the production matcher.
ALIAS_VERSION = "country-alias-counterfactual-v1"
COUNTRY_ALIASES = {
    "us": "united states",
    "usa": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "great britain": "united kingdom",
}


def _normal(value: str) -> str:
    # Match PostgreSQL btrim(text), which trims ASCII spaces, not all whitespace.
    return value.strip(" ").lower()


def canonical_country(value: str) -> str:
    normal = _normal(value)
    return COUNTRY_ALIASES.get(normal, normal)


def alias_criteria(criteria: CompiledCriteria) -> CompiledCriteria:
    return replace(
        criteria,
        countries=tuple(map(canonical_country, criteria.countries)),
        excluded_countries=tuple(map(canonical_country, criteria.excluded_countries)),
    )


def missing_fields(company: CompanyAttributes) -> tuple[str, ...]:
    fields = []
    if not any(
        v is not None and _normal(v) not in {"", "unspecified"}
        for v in (company.business_sector or ())
    ):
        fields.append("business_sector")
    if company.company_scale not in {"0-10", "11-100", "101-1000", "1001+"}:
        fields.append("company_scale")
    if company.country is None or not company.country.strip(" "):
        fields.append("country")
    return tuple(fields)


def gate_failures(
    companies: tuple[CompanyAttributes, ...],
    facts: tuple[SourceFact, ...],
    criteria: CompiledCriteria,
    window: SignalWindow,
) -> dict[str, int]:
    """Return overlapping eligibility gate diagnostics for frozen inputs."""
    by_company = defaultdict(list)
    for fact in facts:
        by_company[fact.company_id].append(fact)
    counts = Counter()
    for company in companies:
        evidence = by_company[company.company_id]
        if not evidence:
            counts["no_guarded_source"] += 1
        if not any(
            f.occurred_at is not None and window.cutoff <= f.occurred_at <= window.as_of
            for f in evidence
        ):
            counts["no_evidence_in_event_window"] += 1
        sectors = {
            _normal(s)
            for s in (company.business_sector or ())
            if s is not None and _normal(s) not in {"", "unspecified"}
        }
        if not sectors.intersection(map(_normal, criteria.industries)):
            counts["sector"] += 1
        if company.company_scale not in criteria.company_sizes:
            counts["size"] += 1
        country = _normal(company.country) if company.country is not None else None
        if not country or country not in set(map(_normal, criteria.countries)):
            counts["country"] += 1
        if (
            company.company_id in criteria.excluded_company_ids
            or sectors.intersection(map(_normal, criteria.excluded_industries))
            or (
                country is not None
                and country in set(map(_normal, criteria.excluded_countries))
            )
        ):
            counts["exclusions"] += 1
    return dict(sorted(counts.items()))
