from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StagedSignal:
    """One row read back from either per-source staging table, tagged
    with its source so `SignalResolver` can build a placeholder key
    without the reader needing to know about resolution at all.
    """

    source: str
    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str | None
    occurred_on: datetime
    url: str
    # Nullable source-specific fields on silver.resolved_signals. HN has
    # none; company_status is supplied by YC and EU-Startups.
    company_status: str | None = None
    team_size: int | None = None
    industries: tuple[str, ...] | None = None
    all_locations: str | None = None
    # YC's prior names, verbatim and uncleaned. See
    # db/schema/silver-yc-former-names.sql: captured for a future name-based
    # matcher (KAN-4), not read by any current resolution logic.
    former_names: tuple[str, ...] | None = None
    # YC's funded batch, verbatim. See the note on YcListingStaging.batch.
    batch: str | None = None
    # EU-Startups' source text, carried raw through resolution to Gold.
    founded: str | None = None
    total_funding: str | None = None
