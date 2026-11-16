from dataclasses import replace

import pytest

from huginn.management.application.policies.recommendation_preferences import (
    validate_exclusions,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.matchmaking.domain.policies.business_company_fit import (
    country_preference,
    is_explicitly_excluded,
)
from tests.management.application.recommendation_fixtures import recommendation_company


def test_country_aliases_share_preference_and_exclusion_identity():
    for actual in ("US", "USA", "United States of America", "United States"):
        assert (
            country_preference(actual, [{"kind": "country", "value": "United States"}])
            == "match"
        )
        company = replace(recommendation_company(), country=actual)
        assert is_explicitly_excluded(
            company.company_id,
            company.business_sector,
            company.country,
            [{"kind": "geography", "geography": {"kind": "country", "value": "USA"}}],
        )
    assert country_preference(None, [{"kind": "country", "value": "US"}]) == "unknown"
    assert (
        country_preference("unknown value", [{"kind": "country", "value": "US"}])
        == "unknown"
    )
    assert (
        country_preference("UK", [{"kind": "country", "value": "United Kingdom"}])
        == "match"
    )


def test_undefined_regions_are_unknown_preferences_but_never_ignored_exclusions():
    assert (
        country_preference("US", [{"kind": "region", "value": "North America"}])
        == "unknown"
    )
    with pytest.raises(ValidationDomainError, match="country"):
        validate_exclusions(
            [
                {
                    "kind": "geography",
                    "geography": {"kind": "region", "value": "North America"},
                }
            ]
        )
