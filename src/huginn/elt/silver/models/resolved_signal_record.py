from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ResolvedSignalRecord:
    """One row to upsert into silver.resolved_signals, produced by
    `resolve_signal` from a `StagedSignal`.
    """

    source: str
    source_stable_id: str
    resolved_company_key: str
    company_name_raw: str
    signal_type: str
    stage: str | None
    description: str | None
    occurred_on: datetime
    url: str
    key_derivation: str
    # Source-specific fields on the shared event record. YC and EU-Startups
    # supply company_status; EU-Startups also supplies founded and
    # total_funding. HN supplies none of these profile/tracking values.
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
    # EU-Startups tracking values, kept raw until Gold applies attribution.
    founded: str | None = None
    total_funding: str | None = None
