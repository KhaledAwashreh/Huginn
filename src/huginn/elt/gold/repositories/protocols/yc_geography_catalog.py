"""Ports required to build and cache the YC geography catalog."""

from pathlib import Path
from typing import Protocol

from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog


class YcFacetQueryPort(Protocol):
    def query(self, body: dict) -> dict: ...


class CountryReferencePort(Protocol):
    @property
    def version(self) -> str: ...

    def country_names(self) -> frozenset[str]: ...


class GeographyCatalogStore(Protocol):
    def save(self, path: Path, catalog: YcGeographyCatalog) -> None: ...

    def load(self, path: Path) -> YcGeographyCatalog: ...
