"""Explicit operator refresh for the frozen YC geography catalog."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from huginn.elt.gold.infrastructure.pycountry_reference import PycountryReference
from huginn.elt.gold.infrastructure.yc_geography_catalog_store import (
    JsonGeographyCatalogStore,
)
from huginn.elt.gold.services.yc_geography_catalog import refresh_yc_geography_catalog
from huginn.elt.ingestion.adapters.yc import YC_ALGOLIA_APP_ID, YC_ALGOLIA_INDEX
from huginn.elt.ingestion.connectors.algolia import AlgoliaConnector


def main(
    argv: Sequence[str] | None = None,
    *,
    connector_factory: Callable[[str], object] | None = None,
    reference_factory: Callable[[], object] | None = None,
    store_factory: Callable[[], object] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the local YC geography catalog."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.environ.get("HUGINN_YC_ALGOLIA_API_KEY")
        if not api_key:
            raise RuntimeError("HUGINN_YC_ALGOLIA_API_KEY is required")
        query = (
            connector_factory
            or (lambda key: AlgoliaConnector(YC_ALGOLIA_APP_ID, YC_ALGOLIA_INDEX, key))
        )(api_key)
        reference = (reference_factory or PycountryReference)()
        store = (store_factory or JsonGeographyCatalogStore)()
        refresh_yc_geography_catalog(query, reference, store, args.output)
        return 0
    except Exception as error:
        sys.stderr.write(
            f"YC geography catalog refresh failed: {type(error).__name__}\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
