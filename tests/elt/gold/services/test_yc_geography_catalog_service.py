import pytest

from huginn.elt.gold.infrastructure.yc_geography_catalog_store import (
    JsonGeographyCatalogStore,
)
from huginn.elt.gold.models.catalog_region import CatalogRegion
from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog
from huginn.elt.gold.services.yc_geography_catalog import refresh_yc_geography_catalog


class Query:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def query(self, body):
        self.calls.append(body)
        return self.response


class Reference:
    version = "reference-v1"

    def country_names(self):
        return frozenset({"Germany", "Georgia", "United States"})


class Store:
    def __init__(self):
        self.saved = None

    def save(self, path, catalog):
        self.saved = catalog

    def load(self, path):
        raise NotImplementedError


def test_refresh_uses_zero_hit_regions_facet_and_freezes_exact_labels(tmp_path):
    query = Query(
        {
            "exhaustiveFacetsCount": True,
            "exhaustive": {"facetsCount": True, "nbHits": True, "typo": True},
            "facets": {"regions": {"Germany": 7, "Georgia": 2, "Africa": 1}},
        }
    )
    store = Store()
    result = refresh_yc_geography_catalog(
        query, Reference(), store, tmp_path / "catalog.json"
    )
    assert query.calls == [
        {
            "query": "",
            "facets": ["regions"],
            "hitsPerPage": 0,
            "maxValuesPerFacet": 1000,
        }
    ]
    assert result == store.saved
    assert result.country_labels == ("Germany",)
    assert result.ambiguous_labels == ("Georgia",)
    assert result.unknown_labels == ("Africa",)
    assert result.regions[0].label == "Africa"


def test_failed_query_does_not_overwrite_previous_cache(tmp_path):
    path = tmp_path / "cache.json"
    existing = YcGeographyCatalog.create(
        (CatalogRegion("Germany", 2),),
        country_labels=("Germany",),
        unknown_labels=(),
        ambiguous_labels=(),
        fetched_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        reference_version="reference-v1",
    )
    file_store = JsonGeographyCatalogStore()
    file_store.save(path, existing)
    original = path.read_bytes()

    class FailingQuery:
        def query(self, body):
            raise RuntimeError("network failed")

    with pytest.raises(RuntimeError):
        refresh_yc_geography_catalog(FailingQuery(), Reference(), file_store, path)
    assert path.read_bytes() == original
