"""One exact YC region facet label and its observed hit count."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogRegion:
    label: str
    count: int
