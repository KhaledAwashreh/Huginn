from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class YcListingStaging:
    """One row of silver.yc_listings. See docs/entities.md's YcListingStaging."""

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str | None
    occurred_on: datetime
    url: str
    # YC-only staging columns. HN's freeform comments have neither a
    # registry status nor a headcount, so these exist on
    # silver.yc_listings alone. ADR-0001 anticipated a source-specific
    # staging column rather than a nullable column on every source.
    company_status: str | None = None
    team_size: int | None = None
    industries: tuple[str, ...] | None = None
    all_locations: str | None = None
    # YC's prior names, verbatim and uncleaned. See
    # db/schema/silver-yc-former-names.sql: captured for a future name-based
    # matcher (KAN-4), not read by any current resolution logic.
    former_names: tuple[str, ...] | None = None
    # YC's `batch` verbatim, e.g. 'Winter 2022': the funded batch the company
    # joined YC in. Distinct from `occurred_on`, which is YC's `launched_at`,
    # a largely independent date. See db/schema/silver-yc-batch.sql.
    batch: str | None = None
