from dataclasses import replace

import pytest

from huginn.management.application.policies.recommendation_preferences import (
    country_preference,
    excluded_from_research,
    validate_exclusions,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from tests.management.test_recommendation_service import Store


def test_country_aliases_share_preference_and_exclusion_identity():
    for actual in ("US", "USA", "United States of America", "United States"):
        assert (
            country_preference(actual, [{"kind": "country", "value": "United States"}])
            == "match"
        )
        company = replace(Store().company, country=actual)
        assert excluded_from_research(
            company,
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
