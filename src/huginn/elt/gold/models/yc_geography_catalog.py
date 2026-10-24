"""Frozen YC geography snapshot value. See architecture document section 4.3."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from huginn.elt.gold.constants.yc_geography_catalog import (
    CATALOG_SCHEMA_VERSION,
    CLASSIFIER_VERSION,
)
from huginn.elt.gold.models.catalog_region import CatalogRegion


@dataclass(frozen=True)
class YcGeographyCatalog:
    schema_version: str
    classifier_version: str
    reference_version: str
    fetched_at: datetime
    regions: tuple[CatalogRegion, ...]
    country_labels: tuple[str, ...]
    unknown_labels: tuple[str, ...]
    ambiguous_labels: tuple[str, ...]
    fingerprint: str

    @classmethod
    def create(
        cls,
        regions: tuple[CatalogRegion, ...],
        *,
        country_labels: tuple[str, ...],
        unknown_labels: tuple[str, ...],
        ambiguous_labels: tuple[str, ...],
        fetched_at: datetime,
        reference_version: str,
    ) -> YcGeographyCatalog:
        ordered = tuple(sorted(regions, key=lambda item: item.label))
        fields = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "classifier_version": CLASSIFIER_VERSION,
            "reference_version": reference_version,
            "fetched_at": fetched_at.isoformat(),
            "regions": [(item.label, item.count) for item in ordered],
            "country_labels": sorted(country_labels),
            "unknown_labels": sorted(unknown_labels),
            "ambiguous_labels": sorted(ambiguous_labels),
        }
        fingerprint = hashlib.sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            CATALOG_SCHEMA_VERSION,
            CLASSIFIER_VERSION,
            reference_version,
            fetched_at,
            ordered,
            tuple(fields["country_labels"]),
            tuple(fields["unknown_labels"]),
            tuple(fields["ambiguous_labels"]),
            fingerprint,
        )
