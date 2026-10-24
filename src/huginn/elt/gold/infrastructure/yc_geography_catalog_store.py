"""Atomic local JSON cache for frozen YC geography catalogs."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from huginn.elt.gold.constants.yc_geography_catalog import (
    CATALOG_SCHEMA_VERSION,
    CLASSIFIER_VERSION,
    MAX_FACET_VALUES,
)
from huginn.elt.gold.models.catalog_region import CatalogRegion
from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog


class JsonGeographyCatalogStore:
    def save(self, path: Path, catalog: YcGeographyCatalog) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".yc-geography-", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(catalog_to_dict(catalog), stream, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def load(self, path: Path) -> YcGeographyCatalog:
        raw = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "schema_version",
            "classifier_version",
            "reference_version",
            "fetched_at",
            "regions",
            "country_labels",
            "unknown_labels",
            "ambiguous_labels",
            "fingerprint",
        }
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("invalid YC geography catalog structure")
        if (
            raw["schema_version"] != CATALOG_SCHEMA_VERSION
            or raw["classifier_version"] != CLASSIFIER_VERSION
        ):
            raise ValueError("unsupported YC geography catalog version")
        if not all(
            isinstance(raw[name], str) and raw[name]
            for name in ("reference_version", "fingerprint")
        ):
            raise ValueError("invalid YC geography catalog metadata")
        try:
            fetched_at = datetime.fromisoformat(raw["fetched_at"])
        except (TypeError, ValueError) as error:
            raise ValueError("invalid catalog fetched_at") from error
        if fetched_at.tzinfo is None:
            raise ValueError("catalog fetched_at must be timezone-aware")
        if (
            not isinstance(raw["regions"], list)
            or not raw["regions"]
            or len(raw["regions"]) >= MAX_FACET_VALUES
        ):
            raise ValueError("invalid catalog regions")
        regions = []
        for item in raw["regions"]:
            if not isinstance(item, dict) or set(item) != {"label", "count"}:
                raise ValueError("invalid catalog region")
            label, count = item["label"], item["count"]
            if (
                not isinstance(label, str)
                or not label.strip()
                or len(label) >= 1000
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
            ):
                raise ValueError("invalid catalog region value")
            regions.append(CatalogRegion(label, count))
        region_labels = [item.label for item in regions]
        if region_labels != sorted(set(region_labels)):
            raise ValueError("catalog regions must be unique and sorted")
        classifications = []
        for name in ("country_labels", "unknown_labels", "ambiguous_labels"):
            values = raw[name]
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError("invalid catalog classification")
            if values != sorted(set(values)):
                raise ValueError("catalog classifications must be unique and sorted")
            classifications.append(tuple(values))
        country, unknown, ambiguous = map(set, classifications)
        region_set = set(region_labels)
        us_aliases = {"USA", "United States", "United States of America"}
        if country & unknown or country & ambiguous or unknown & ambiguous:
            raise ValueError("catalog classifications overlap")
        observed_us = country & region_set & us_aliases
        if "Georgia" in country or not (country - region_set) <= us_aliases:
            raise ValueError("invalid trusted catalog country labels")
        if (country - region_set) and not observed_us:
            raise ValueError("unobserved US aliases require an observed US label")
        if (unknown | ambiguous | country.intersection(region_set)) != region_set or (
            "Georgia" in region_set and "Georgia" not in ambiguous
        ):
            raise ValueError("catalog classifications do not match region labels")
        expected = YcGeographyCatalog.create(
            tuple(regions),
            country_labels=classifications[0],
            unknown_labels=classifications[1],
            ambiguous_labels=classifications[2],
            fetched_at=fetched_at,
            reference_version=raw["reference_version"],
        )
        if expected.fingerprint != raw["fingerprint"]:
            raise ValueError("YC geography catalog fingerprint mismatch")
        return expected


def catalog_to_dict(catalog: YcGeographyCatalog) -> dict[str, object]:
    return {
        "schema_version": catalog.schema_version,
        "classifier_version": catalog.classifier_version,
        "reference_version": catalog.reference_version,
        "fetched_at": catalog.fetched_at.isoformat(),
        "regions": [
            {"label": item.label, "count": item.count} for item in catalog.regions
        ],
        "country_labels": list(catalog.country_labels),
        "unknown_labels": list(catalog.unknown_labels),
        "ambiguous_labels": list(catalog.ambiguous_labels),
        "fingerprint": catalog.fingerprint,
    }
