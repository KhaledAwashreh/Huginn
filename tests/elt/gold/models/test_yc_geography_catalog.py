from datetime import UTC, datetime

from huginn.elt.gold.models.catalog_region import CatalogRegion
from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog


def test_catalog_fingerprint_binds_region_counts_and_classification_versions():
    fetched = datetime(2026, 10, 24, tzinfo=UTC)
    catalog = YcGeographyCatalog.create(
        (CatalogRegion("Germany", 4),),
        country_labels=("Germany",),
        unknown_labels=(),
        ambiguous_labels=("Georgia",),
        fetched_at=fetched,
        reference_version="2026.10",
    )
    changed = YcGeographyCatalog.create(
        (CatalogRegion("Germany", 5),),
        country_labels=("Germany",),
        unknown_labels=(),
        ambiguous_labels=("Georgia",),
        fetched_at=fetched,
        reference_version="2026.10",
    )
    assert catalog.fingerprint != changed.fingerprint
