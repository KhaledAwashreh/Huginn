import pytest

from huginn.elt.gold.models.catalog_region import CatalogRegion
from huginn.elt.gold.policies.yc_geography_catalog import (
    classify_region_labels,
    parse_region_facet,
)

COUNTRIES = frozenset({"Germany", "Georgia", "United States", "United Kingdom"})


def response(labels):
    return {
        "exhaustiveFacetsCount": True,
        "facets": {"regions": labels},
        "exhaustive": {"facetsCount": True, "nbHits": True, "typo": True},
    }


def test_region_facet_exact_names_keep_unknown_and_ambiguous_labels():
    regions = parse_region_facet(
        response({"Germany": 5, "Georgia": 4, "Africa": 3, "Berlin, Germany": 2})
    )
    countries, unknown, ambiguous = classify_region_labels(regions, COUNTRIES)
    assert countries == ("Germany",)
    assert unknown == ("Africa", "Berlin, Germany")
    assert ambiguous == ("Georgia",)


def test_us_source_variants_are_added_only_when_a_variant_was_observed():
    labels = parse_region_facet(response({"USA": 2, "Remote": 1}))
    countries, _, _ = classify_region_labels(labels, COUNTRIES)
    assert countries == ("USA", "United States", "United States of America")
    labels = parse_region_facet(response({"Germany": 2}))
    countries, _, _ = classify_region_labels(labels, COUNTRIES)
    assert countries == ("Germany",)


def test_reviewed_aliases_match_reference_but_preserve_source_label():
    labels = parse_region_facet(
        response(
            {
                "Ivory Coast": 1,
                "Democratic Republic of the Congo": 1,
                "Turkey": 1,
                "Russia": 1,
            }
        )
    )
    countries, unknown, ambiguous = classify_region_labels(
        labels,
        COUNTRIES
        | {
            "Côte d'Ivoire",
            "Congo, The Democratic Republic of the",
            "Türkiye",
            "Russian Federation",
        },
    )
    assert countries == (
        "Democratic Republic of the Congo",
        "Ivory Coast",
        "Russia",
        "Turkey",
    )
    assert unknown == ambiguous == ()


@pytest.mark.parametrize(
    "document",
    [
        {"exhaustiveFacetsCount": False},
        {"exhaustiveFacetsCount": "yes"},
        {
            "exhaustiveFacetsCount": True,
            "exhaustive": {"facetsCount": True, "facetValues": False},
        },
        {"exhaustiveFacetsCount": True, "exhaustive": {"facetsCount": "yes"}},
    ],
)
def test_unproven_or_malformed_facet_metadata_is_rejected(document):
    with pytest.raises(ValueError):
        parse_region_facet({**document, "facets": {"regions": {"Germany": 1}}})


def test_counts_and_facet_caps_are_validated():
    for labels in (
        {str(i): 1 for i in range(1000)},
        {"x" * 1000: 1},
        {"x": True},
        {"x": -1},
    ):
        with pytest.raises(ValueError):
            parse_region_facet(response(labels))
    assert parse_region_facet(response({"Germany": 1})) == (
        CatalogRegion("Germany", 1),
    )
