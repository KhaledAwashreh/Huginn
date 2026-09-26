"""Silver data shapes. See architecture document section 5.

Separated from `ports.py` so the protocols file holds contracts only and
the data a contract passes around has its own home, matching the
`models.py` / `ports.py` / `repositories/` shape Silver's own package
now uses throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HnPostingStaging:
    """One row of silver.hn_postings. See docs/entities.md's HnPostingStaging."""

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str


@dataclass(frozen=True)
class YcListingStaging:
    """One row of silver.yc_listings. See docs/entities.md's YcListingStaging."""

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
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


@dataclass(frozen=True)
class EuStartupsListingStaging:
    """One row of silver.eu_startups_listings. Same per-source staging
    shape as HnPostingStaging/YcListingStaging (docs/entities.md's Silver
    section: "Additional per-source staging tables follow this same
    shape"). Jira KAN-64. `stage` and `occurred_on` don't map naturally
    from a directory listing; see huginn.elt.silver.eu_startups_staging's
    `parse_eu_startups_listing` for what is stored there instead.
    """

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str


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
    description: str
    occurred_on: datetime
    url: str
    # YC-shaped by circumstance, not by design: this is the cross-source
    # read shape, so an HN staged signal has None for both. Mirrors the
    # nullable columns on silver.resolved_signals.
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
    description: str
    occurred_on: datetime
    url: str
    key_derivation: str
    # YC-shaped by circumstance, not by design: an HN row has None for
    # all of these, since "Who's Hiring" comments carry no registry status,
    # no headcount, no industry list, and no location.
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
