"""Acceptance from retained Brightroom HTML; no synthetic HN/YC source claims.

Country and text come from the fixture. Size and industry remain unknown;
listing tags are not invented company attributes or evidence of buyer need.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from huginn.elt.silver.normalizers.eu_startups_context import normalize_eu_startups
from huginn.matchmaking.domain.policies.business_company_fit import (
    assess_company_fit,
)
from huginn.matchmaking.domain.policies.lexical_research import (
    assess_topic_overlap,
    offering_terms,
)
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)

AS_OF = datetime(2026, 10, 28, tzinfo=UTC)


def _observation(extraction, occurred_at):
    return RankingObservation(
        observation_id=uuid4(),
        description=extraction.normalized_text,
        occurred_at=occurred_at,
        observed_at=AS_OF,
        source=extraction.source,
        source_url=extraction.source_url,
    )


def _retained_listing():
    fixture = (
        Path(__file__).parents[3]
        / "fixtures"
        / "eu_startups"
        / "listing_brightroom.html"
    )
    extraction = normalize_eu_startups(
        {
            "url": "https://www.eu-startups.com/directory/brightroom/",
            "html": fixture.read_text(encoding="utf-8"),
        }
    )
    assert extraction.status == "captured"
    assert extraction.source_fields["category"] == "Germany"
    assert "team_size" not in extraction.source_fields
    assert "industries" not in extraction.source_fields
    return extraction


@pytest.mark.parametrize("country", ["DE", "Germany", "DEU"])
def test_retained_country_aliases_completely_satisfy_configured_fit(country):
    extraction = _retained_listing()
    fit = assess_company_fit(
        uuid4(),
        None,
        None,
        extraction.source_fields["category"],
        {"geographies": [{"kind": "country", "value": country}]},
    )
    assert dict(fit.dimensions) == {"country": "match"}
    assert fit.eligible is True
    assert fit.explicitly_excluded is False


def test_missing_industry_and_size_stay_unknown_with_retained_lexical_evidence():
    extraction = _retained_listing()
    company_id = uuid4()
    fit = assess_company_fit(
        company_id,
        None,
        None,
        extraction.source_fields["category"],
        {
            "industries": [{"name": "Software"}],
            "company_sizes": [{"band": "11-100"}],
            "geographies": [{"kind": "country", "value": "DE"}],
        },
    )
    observation = _observation(extraction, None)
    assessment = assess_topic_overlap(
        company_id,
        (observation,),
        offering_terms("career coaching marketplace"),
        AS_OF,
        industry_match=fit.industry,
        size_match=fit.size,
        country_match=fit.country,
        service_terms=offering_terms("coaching"),
    )
    assert dict(fit.dimensions) == {
        "industry": "unknown",
        "size": "unknown",
        "country": "match",
    }
    assert fit.eligible is True
    assert assessment is not None
    assert assessment.service_fit == "adjacent"
    assert assessment.service_basis == "inferred"
    assert assessment.business_context == "unknown"
    assert assessment.industry_match == assessment.size_match == "unknown"
    assert assessment.country_match == "match"
    assert assessment.observations == (observation,)
    assert observation.source_url == "https://www.eu-startups.com/directory/brightroom/"
    assert assessment.evidence[0].observation_id == observation.observation_id
    quote = assessment.evidence[0].quote
    assert "coaching" in quote
    assert quote in extraction.normalized_text
    assert "coaching marketplace for individual professionals" in quote


def test_known_retained_country_mismatch_rejects_despite_unknown_size():
    extraction = _retained_listing()
    fit = assess_company_fit(
        uuid4(),
        None,
        None,
        extraction.source_fields["category"],
        {
            "company_sizes": [{"band": "11-100"}],
            "geographies": [{"kind": "country", "value": "US"}],
        },
    )
    assert dict(fit.dimensions) == {"size": "unknown", "country": "mismatch"}
    assert fit.eligible is False
    assert fit.explicitly_excluded is False


@pytest.mark.parametrize("kind", ["company", "geography"])
def test_explicit_exclusion_overrides_matching_retained_country(kind):
    extraction = _retained_listing()
    company_id = uuid4()
    exclusion = (
        {"kind": "company", "company_id": str(company_id)}
        if kind == "company"
        else {"kind": "geography", "geography": {"kind": "country", "value": "DEU"}}
    )
    fit = assess_company_fit(
        company_id,
        None,
        None,
        extraction.source_fields["category"],
        {
            "geographies": [{"kind": "country", "value": "Germany"}],
            "exclusions": [exclusion],
        },
    )
    assert fit.country == "match"
    assert fit.explicitly_excluded is True
    assert fit.eligible is False
