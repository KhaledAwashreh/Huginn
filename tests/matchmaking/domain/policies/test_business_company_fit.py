from huginn.matchmaking.domain.policies.business_company_fit import (
    assess_company_fit,
    country_preference,
    is_explicitly_excluded,
    normalize_country,
)


def test_company_fit_distinguishes_unknown_attributes_from_mismatches():
    icp = {
        "industries": [{"name": "Software"}],
        "company_sizes": [{"band": "11-100"}],
        "geographies": [{"kind": "country", "value": "United States"}],
    }
    unknown_size = assess_company_fit("id", ("Software",), None, "USA", icp)
    assert unknown_size.industry == "match"
    assert unknown_size.size == "unknown"
    assert unknown_size.country == "match"
    assert unknown_size.eligible is True
    mismatch = assess_company_fit("id", ("Software",), "0-10", "USA", icp)
    assert mismatch.size == "mismatch"
    assert mismatch.eligible is False


def test_company_fit_uses_country_aliases_and_keeps_unknown_countries_unknown():
    assert normalize_country("USA") == normalize_country("United States") == "US"
    assert (
        country_preference("UK", [{"kind": "country", "value": "United Kingdom"}])
        == "match"
    )
    assert country_preference(None, [{"kind": "country", "value": "US"}]) == "unknown"
    assert country_preference("CA", [{"kind": "country", "value": "US"}]) == "mismatch"


def test_explicit_company_industry_and_country_exclusions_are_independent():
    company_id = "6f9e31fd-e043-48e5-b7b6-d0a5b896b33e"
    assert is_explicitly_excluded(
        company_id, ("Software",), "US", [{"kind": "company", "company_id": company_id}]
    )
    assert is_explicitly_excluded(
        company_id, ("Software",), "US", [{"kind": "industry", "name": "software"}]
    )
    assert is_explicitly_excluded(
        company_id,
        ("Software",),
        "United States",
        [{"kind": "geography", "geography": {"kind": "country", "value": "USA"}}],
    )
    assert not is_explicitly_excluded(company_id, ("Software",), "US", [])
