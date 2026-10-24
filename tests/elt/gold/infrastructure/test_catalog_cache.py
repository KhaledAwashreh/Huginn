import json
from datetime import UTC, datetime

import pytest

from huginn.elt.gold.infrastructure.yc_geography_catalog_store import (
    JsonGeographyCatalogStore,
)
from huginn.elt.gold.models.catalog_region import CatalogRegion
from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog


def catalog():
    return YcGeographyCatalog.create(
        (
            CatalogRegion("Germany", 7),
            CatalogRegion("Georgia", 2),
            CatalogRegion("Remote", 1),
        ),
        country_labels=("Germany",),
        unknown_labels=("Remote",),
        ambiguous_labels=("Georgia",),
        fetched_at=datetime(2026, 10, 24, tzinfo=UTC),
        reference_version="test-ref",
    )


def test_cache_round_trip_and_load_does_not_reclassify(tmp_path):
    store = JsonGeographyCatalogStore()
    path = tmp_path / "cache" / "catalog.json"
    store.save(path, catalog())
    assert store.load(path) == catalog()
    assert not list(path.parent.glob(".yc-geography-*"))


def test_cache_rejects_fingerprint_schema_and_inconsistent_content(tmp_path):
    store = JsonGeographyCatalogStore()
    path = tmp_path / "catalog.json"
    store.save(path, catalog())
    raw = json.loads(path.read_text())
    raw["regions"][0]["count"] += 1
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="fingerprint"):
        store.load(path)
    raw["regions"][0]["count"] -= 1
    raw["schema_version"] = "future"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="version"):
        store.load(path)
    raw["schema_version"] = catalog().schema_version
    raw["country_labels"] = ["Narnia"]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="trusted catalog country"):
        store.load(path)


def test_cache_rejects_unobserved_us_alias_without_observed_us_variant(tmp_path):
    store = JsonGeographyCatalogStore()
    path = tmp_path / "catalog.json"
    altered = YcGeographyCatalog.create(
        (
            CatalogRegion("Germany", 7),
            CatalogRegion("Georgia", 2),
            CatalogRegion("Remote", 1),
        ),
        country_labels=("Germany", "USA"),
        unknown_labels=("Remote",),
        ambiguous_labels=("Georgia",),
        fetched_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        reference_version="test-ref",
    )
    store.save(path, altered)
    raw = json.loads(path.read_text())
    raw["country_labels"] = ["Germany", "USA"]
    raw["fingerprint"] = YcGeographyCatalog.create(
        altered.regions,
        country_labels=("Germany", "USA"),
        unknown_labels=("Remote",),
        ambiguous_labels=("Georgia",),
        fetched_at=altered.fetched_at,
        reference_version="test-ref",
    ).fingerprint
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="unobserved US aliases"):
        store.load(path)


def test_atomic_replace_failure_keeps_old_cache_and_removes_temp_file(
    tmp_path, monkeypatch
):
    import huginn.elt.gold.infrastructure.yc_geography_catalog_store as cache_module

    store = JsonGeographyCatalogStore()
    path = tmp_path / "catalog.json"
    store.save(path, catalog())
    original = path.read_bytes()
    monkeypatch.setattr(
        cache_module.os,
        "replace",
        lambda *args: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(OSError, match="replace failed"):
        store.save(path, catalog())
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".yc-geography-*"))
