"""Orchestrate one bounded YC region facet refresh and cache write."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog
from huginn.elt.gold.policies.yc_geography_catalog import (
    classify_region_labels,
    parse_region_facet,
)
from huginn.elt.gold.repositories.protocols.yc_geography_catalog import (
    CountryReferencePort,
    GeographyCatalogStore,
    YcFacetQueryPort,
)

logger = logging.getLogger(__name__)


def refresh_yc_geography_catalog(
    query: YcFacetQueryPort,
    reference: CountryReferencePort,
    store: GeographyCatalogStore,
    path: Path,
) -> YcGeographyCatalog:
    logger.info("yc geography refresh: querying regions facet")
    response = query.query(
        {
            "query": "",
            "facets": ["regions"],
            "hitsPerPage": 0,
            "maxValuesPerFacet": 1000,
        }
    )
    regions = parse_region_facet(response)
    countries, unknown, ambiguous = classify_region_labels(
        regions, reference.country_names()
    )
    catalog = YcGeographyCatalog.create(
        regions,
        country_labels=countries,
        unknown_labels=unknown,
        ambiguous_labels=ambiguous,
        fetched_at=datetime.now(UTC),
        reference_version=reference.version,
    )
    store.save(path, catalog)
    logger.info("yc geography refresh: cached %d region labels", len(regions))
    return catalog
