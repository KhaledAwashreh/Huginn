"""Read-only installed pycountry reference adapter."""

from __future__ import annotations

import importlib.metadata

import pycountry


class PycountryReference:
    @property
    def version(self) -> str:
        return importlib.metadata.version("pycountry")

    def country_names(self) -> frozenset[str]:
        return frozenset(
            name
            for country in pycountry.countries
            for name in (
                country.name,
                getattr(country, "official_name", None),
                getattr(country, "common_name", None),
            )
            if name
        )
