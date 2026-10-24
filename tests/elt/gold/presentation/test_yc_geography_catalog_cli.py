import json
from datetime import UTC, datetime

from huginn.elt.gold.infrastructure.yc_geography_catalog_store import (
    JsonGeographyCatalogStore,
)
from huginn.elt.gold.presentation.cli.attribute_assessment import (
    main as assessment_main,
)
from huginn.elt.gold.presentation.cli.yc_geography_catalog import main as refresh_main
from tests.elt.gold.services.test_attribute_assessment_service import Repository


def test_refresh_cli_uses_existing_connector_query_and_writes_catalog(
    tmp_path, monkeypatch
):
    output = tmp_path / "catalog.json"
    monkeypatch.setenv("HUGINN_YC_ALGOLIA_API_KEY", "test-key")
    calls = []

    class Connector:
        def query(self, body):
            calls.append(body)
            return {
                "exhaustiveFacetsCount": True,
                "facets": {"regions": {"Germany": 5, "Georgia": 1}},
            }

    class Reference:
        version = "test-reference"

        def country_names(self):
            return frozenset({"Germany", "Georgia"})

    assert (
        refresh_main(
            ["--output", str(output)],
            connector_factory=lambda key: Connector(),
            reference_factory=Reference,
        )
        == 0
    )
    assert calls == [
        {
            "query": "",
            "facets": ["regions"],
            "hitsPerPage": 0,
            "maxValuesPerFacet": 1000,
        }
    ]
    raw = json.loads(output.read_text())
    assert raw["regions"] == [
        {"label": "Georgia", "count": 1},
        {"label": "Germany", "count": 5},
    ]


def test_assessment_cli_loads_catalog_locally_without_api_call(tmp_path, monkeypatch):
    from huginn.elt.gold.infrastructure.pycountry_reference import PycountryReference
    from huginn.elt.gold.models.catalog_region import CatalogRegion
    from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog
    from huginn.elt.ingestion.connectors.algolia import AlgoliaConnector

    monkeypatch.setattr(
        AlgoliaConnector,
        "query",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("assessment must not query Algolia")
        ),
    )
    monkeypatch.setattr(
        PycountryReference,
        "country_names",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("cache load must not reclassify")
        ),
    )
    catalog_path = tmp_path / "catalog.json"
    catalog = YcGeographyCatalog.create(
        (CatalogRegion("Germany", 1), CatalogRegion("Georgia", 1)),
        country_labels=("Germany",),
        unknown_labels=(),
        ambiguous_labels=("Georgia",),
        fetched_at=datetime.now(UTC),
        reference_version="test-reference",
    )
    JsonGeographyCatalogStore().save(catalog_path, catalog)
    summary = tmp_path / "summary.json"
    assert (
        assessment_main(
            [
                "--cutoff",
                "2026-09-01T00:00:00Z",
                "--as-of",
                "2026-10-01T00:00:00Z",
                "--summary",
                str(summary),
                "--yc-geography-catalog",
                str(catalog_path),
            ],
            repository_factory=Repository,
        )
        == 0
    )
    report = json.loads(summary.read_text())
    assert report["yc_geography_catalog"] == {
        "fingerprint": catalog.fingerprint,
        "schema_version": catalog.schema_version,
        "classifier_version": catalog.classifier_version,
        "reference_version": catalog.reference_version,
        "fetched_at": catalog.fetched_at.isoformat(),
    }
