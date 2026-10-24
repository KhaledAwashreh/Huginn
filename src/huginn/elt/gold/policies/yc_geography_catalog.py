"""Pure YC geography facet validation and exact-label classification."""

from __future__ import annotations

from collections.abc import Iterable

from huginn.elt.gold.constants.yc_geography_catalog import MAX_FACET_VALUES
from huginn.elt.gold.models.catalog_region import CatalogRegion

# Reviewed variants present in the YC directory, mapped to pycountry names.
_COUNTRY_ALIASES = {
    "Democratic Republic of the Congo": "Congo, The Democratic Republic of the",
    "Ivory Coast": "Côte d'Ivoire",
    "Russia": "Russian Federation",
    "Turkey": "Türkiye",
}
_US_LABELS = frozenset({"USA", "United States", "United States of America"})


def parse_region_facet(response: object) -> tuple[CatalogRegion, ...]:
    if not isinstance(response, dict):
        raise ValueError("Algolia response must be an object")
    facets = response.get("facets")
    if not isinstance(facets, dict) or not isinstance(facets.get("regions"), dict):
        raise ValueError("regions facet is missing")
    legacy = response.get("exhaustiveFacetsCount")
    exhaustive = response.get("exhaustive")
    if legacy is not None and not isinstance(legacy, bool):
        raise ValueError("malformed exhaustive facet count flag")
    if exhaustive is not None and not isinstance(exhaustive, dict):
        raise ValueError("malformed exhaustive metadata")
    flags = []
    if legacy is not None:
        flags.append(legacy)
    if exhaustive is not None:
        for name, value in exhaustive.items():
            if name not in {"facetsCount", "facetValues", "nbHits", "typo"}:
                raise ValueError("unexpected exhaustive metadata")
            if not isinstance(value, bool):
                raise ValueError("malformed exhaustive metadata flag")
            if name in {"facetsCount", "facetValues"}:
                flags.append(value)
    counts_are_exhaustive = legacy is True or (
        isinstance(exhaustive, dict) and exhaustive.get("facetsCount") is True
    )
    if not counts_are_exhaustive or any(flag is False for flag in flags):
        raise ValueError("YC regions facet counts may be truncated")
    values = facets["regions"]
    if not values or len(values) >= MAX_FACET_VALUES:
        raise ValueError("YC regions facet may be truncated")
    result = []
    for label, count in values.items():
        if not isinstance(label, str) or not label.strip() or len(label) >= 1000:
            raise ValueError("invalid or possibly truncated region label")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("invalid regions facet count")
        result.append(CatalogRegion(label, count))
    return tuple(sorted(result, key=lambda item: item.label))


def classify_region_labels(
    regions: tuple[CatalogRegion, ...], country_names: Iterable[str]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    reference = set(country_names)
    countries: set[str] = set()
    unknown: set[str] = set()
    ambiguous: set[str] = set()
    for region in regions:
        label = region.label
        if label == "Georgia":
            ambiguous.add(label)
            continue
        candidate = _COUNTRY_ALIASES.get(
            label, "United States" if label in _US_LABELS else label
        )
        if candidate in reference:
            countries.add(label)
        else:
            unknown.add(label)
    if countries.intersection(_US_LABELS):
        countries.update(_US_LABELS)
    return tuple(sorted(countries)), tuple(sorted(unknown)), tuple(sorted(ambiguous))
