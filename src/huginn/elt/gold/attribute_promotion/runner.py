"""Read-only, frozen-input attribute and matcher counterfactual assessment."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from uuid import UUID

from huginn.elt.gold.attribute_promotion.models import CompanyAttributes, SourceFact
from huginn.elt.gold.attribute_promotion.policy import MAPPING_VERSION, assess
from huginn.elt.gold.attribute_promotion.ports import AttributeAssessmentRepository
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow

FIELDS = ("business_sector", "company_scale", "country")
# Explicit, experimental aliases; never applied by the production matcher.
ALIAS_VERSION = "country-alias-counterfactual-v1"
_ALIASES = {
    "us": "united states",
    "usa": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "great britain": "united kingdom",
}


def json_default(value: object) -> str:
    if isinstance(value, (UUID, datetime, date)):
        return str(value)
    raise TypeError(f"Unsupported report type: {type(value).__name__}")


def _encode(value: object) -> str:
    return json.dumps(
        value, default=json_default, sort_keys=True, separators=(",", ":")
    )


def _normal(value: str) -> str:
    # Match PostgreSQL btrim(text), which trims ASCII spaces, not all whitespace.
    return value.strip(" ").lower()


def _canonical(value: str) -> str:
    normal = _normal(value)
    return _ALIASES.get(normal, normal)


def _alias_criteria(criteria: CompiledCriteria) -> CompiledCriteria:
    return replace(
        criteria,
        countries=tuple(map(_canonical, criteria.countries)),
        excluded_countries=tuple(map(_canonical, criteria.excluded_countries)),
    )


def _missing(company: CompanyAttributes) -> tuple[str, ...]:
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


def _gates(
    companies: tuple[CompanyAttributes, ...],
    facts: tuple[SourceFact, ...],
    criteria: CompiledCriteria,
    window: SignalWindow,
) -> dict[str, int]:
    """Overlapping diagnostics; candidate counts are computed by PostgreSQL."""
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


@dataclass(frozen=True)
class AssessmentResult:
    summary: dict[str, object]
    receipts: tuple[dict[str, object], ...]


def run_assessment(
    repository: AttributeAssessmentRepository,
    criteria: Mapping[str, CompiledCriteria],
    windows: Mapping[str, SignalWindow],
    *,
    limit: int | None = None,
) -> AssessmentResult:
    """Read once, evaluate fills and alias alternatives without changing a row."""
    if not criteria or not windows:
        raise ValueError("At least one synthetic criterion and window is required")
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError("limit must be a positive integer")
    snapshot = repository.read_snapshot(limit)
    companies = tuple(sorted(snapshot.companies, key=lambda c: str(c.company_id)))
    facts = tuple(
        sorted(
            snapshot.facts, key=lambda f: (f.source, f.stable_id, str(f.observation_id))
        )
    )
    grouped: dict[UUID, list[SourceFact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.company_id].append(fact)
    proposals = tuple(p for c in companies for p in assess(c, grouped[c.company_id]))
    changes = defaultdict(dict)
    for proposal in proposals:
        if proposal.status == "proposed":
            changes[proposal.company_id][proposal.field_name] = proposal.proposed_value
    after = tuple(replace(c, **changes[c.company_id]) for c in companies)
    aliased = tuple(
        replace(c, country=None if c.country is None else _canonical(c.country))
        for c in after
    )
    outcomes = {
        field: dict(
            sorted(
                Counter(p.status for p in proposals if p.field_name == field).items()
            )
        )
        for field in FIELDS
    }
    per_source = {}
    for source in sorted({f.source for f in facts}):
        selected = [f for f in facts if f.source == source]
        source_ids = {f.company_id for f in selected}
        per_source[source] = {
            "observations": len(selected),
            "companies": len(source_ids),
            "field_outcomes": {
                field: dict(
                    sorted(
                        Counter(
                            p.status
                            for p in proposals
                            if p.field_name == field and p.company_id in source_ids
                        ).items()
                    )
                )
                for field in FIELDS
            },
        }
    comparisons = []
    for window_name, window in sorted(windows.items()):
        for criteria_name, target in sorted(criteria.items()):
            before_ids = set(
                repository.candidate_ids(snapshot, companies, target, window)
            )
            after_ids = set(repository.candidate_ids(snapshot, after, target, window))
            alias_ids = set(
                repository.candidate_ids(
                    snapshot, aliased, _alias_criteria(target), window
                )
            )
            comparisons.append(
                {
                    "window": window_name,
                    "criteria": criteria_name,
                    "before": len(before_ids),
                    "after": len(after_ids),
                    "newly_eligible": len(after_ids - before_ids),
                    "lost": len(before_ids - after_ids),
                    "unchanged_eligible": len(before_ids & after_ids),
                    "alias_counterfactual": {
                        "after": len(alias_ids),
                        "newly_eligible_vs_fills": len(alias_ids - after_ids),
                        "lost_vs_fills": len(after_ids - alias_ids),
                    },
                    "overlapping_gate_failures_before": _gates(
                        companies, facts, target, window
                    ),
                    "overlapping_gate_failures_after": _gates(
                        after, facts, target, window
                    ),
                }
            )
    fingerprint = hashlib.sha256(
        _encode(
            {
                "companies": [asdict(c) for c in companies],
                "facts": [asdict(f) for f in facts],
            }
        ).encode()
    ).hexdigest()
    windows_report = {
        name: {
            "cutoff": window.cutoff.isoformat(),
            "as_of_inclusive": window.as_of.isoformat(),
        }
        for name, window in sorted(windows.items())
    }
    summary = {
        "status": "complete",
        "mode": "read_only_assessment",
        "mapping_version": MAPPING_VERSION,
        "alias_counterfactual_version": ALIAS_VERSION,
        "alias_counterfactual_mapping": _ALIASES,
        "input_fingerprint": fingerprint,
        "selection": {"limit": limit, "scope": snapshot.scope},
        "company_count": len(companies),
        "guarded_observation_count": len(facts),
        "companies_with_guarded_evidence": sum(
            bool(grouped[c.company_id]) for c in companies
        ),
        "companies_without_guarded_evidence": sum(
            not grouped[c.company_id] for c in companies
        ),
        "field_outcomes": outcomes,
        "guarded_sources": per_source,
        "missing_fields_before": dict(
            sorted(Counter(f for c in companies for f in _missing(c)).items())
        ),
        "missing_fields_after": dict(
            sorted(Counter(f for c in after for f in _missing(c)).items())
        ),
        "windows": windows_report,
        "window_coverage": {
            name: {
                "observations": sum(
                    f.occurred_at is not None
                    and window.cutoff <= f.occurred_at <= window.as_of
                    for f in facts
                ),
                "companies": len(
                    {
                        f.company_id
                        for f in facts
                        if f.occurred_at is not None
                        and window.cutoff <= f.occurred_at <= window.as_of
                    }
                ),
                "null_event_dates": sum(f.occurred_at is None for f in facts),
                "observations_outside_window": sum(
                    f.occurred_at is not None
                    and not window.cutoff <= f.occurred_at <= window.as_of
                    for f in facts
                ),
                "complete_companies_before": sum(
                    not _missing(c)
                    and any(
                        f.occurred_at is not None
                        and window.cutoff <= f.occurred_at <= window.as_of
                        for f in grouped[c.company_id]
                    )
                    for c in companies
                ),
                "complete_companies_after": sum(
                    not _missing(c)
                    and any(
                        f.occurred_at is not None
                        and window.cutoff <= f.occurred_at <= window.as_of
                        for f in grouped[c.company_id]
                    )
                    for c in after
                ),
            }
            for name, window in sorted(windows.items())
        },
        "synthetic_criteria": {
            name: {
                "industries": target.industries,
                "company_sizes": target.company_sizes,
                "countries": target.countries,
                "excluded_industries": target.excluded_industries,
                "excluded_countries": target.excluded_countries,
                "excluded_company_count": len(target.excluded_company_ids),
            }
            for name, target in sorted(criteria.items())
        },
        "comparisons": comparisons,
        "interpretation": "Attribute eligibility only; no probability, ICP usefulness or service demand is inferred. Source coverage is guarded-only; unavailable upstream inputs require a separate source audit. Gate failures overlap. Alias effects are experimental and separate from fills.",
    }
    by_id = {f.observation_id: f for f in facts}
    company_tokens = {
        c.company_id: hashlib.sha256(_encode(asdict(c)).encode()).hexdigest()
        for c in companies
    }
    receipts = tuple(
        {
            **asdict(p),
            "company_id": str(p.company_id),
            "company_input_token": company_tokens[p.company_id],
            "supporting_facts": [asdict(by_id[key]) for key in p.supporting_fact_ids],
        }
        for p in proposals
    )
    return AssessmentResult(summary, receipts)
