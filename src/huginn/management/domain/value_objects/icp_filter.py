"""Independent ICP evaluation dimensions."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IcpCandidateFilter:
    """Flat dimensions preserve OR-within and AND-across evaluation."""

    industries: tuple[dict[str, Any], ...]
    company_sizes: tuple[dict[str, Any], ...]
    geographies: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]
