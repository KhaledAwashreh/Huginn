"""Company/CompanyHistory writer: wires apply_company_update
(huginn.elt.gold.dimensional) to Postgres. Jira KAN-40, ADR-0002,
architecture document section 4.3.
"""

from __future__ import annotations

import logging

from huginn.elt.gold.dimensional import apply_company_update
from huginn.elt.gold.ports import CompanyRepositoryPort

logger = logging.getLogger(__name__)

# The four headcount bands gold.company.company_scale is constrained to.
# Inclusive upper bound, lowest band absorbs team_size=0. Kept as data
# rather than inlined into a chain of comparisons so the boundary values
# read in one place next to the schema constraint they must match.
_SCALE_BANDS: tuple[tuple[int, str], ...] = (
    (10, "0-10"),
    (100, "11-100"),
    (1000, "101-1000"),
)
_SCALE_TOP_BAND = "1001+"


def team_size_to_scale(team_size: int | None) -> str | None:
    """Bucket a headcount into one of gold.company_scale's four bands.

    The bucketing lives in Gold, not in Silver, because the bands are
    Huginn's vocabulary rather than any source's: silver.yc_listings keeps
    `team_size` as the raw integer YC supplies, and this is the single
    place that decides what a headcount means (architecture document
    section 4.3). A second source's headcount can reuse these bands
    without inventing a parallel set.

    Returns None for a missing headcount, which the caller treats as "this
    source does not know" rather than as a value that clears whatever an
    earlier source supplied.
    """
    if team_size is None:
        return None
    for upper, band in _SCALE_BANDS:
        if team_size <= upper:
            return band
    return _SCALE_TOP_BAND


def parse_all_locations(all_locations: str | None) -> tuple[str | None, str | None]:
    """Split YC's `all_locations` into (city, country).

    The field is a human-facing display string, not structured source data,
    so this parse is Huginn's interpretation and lives in Gold rather than in
    Silver (architecture document section 4.3). Its shape, confirmed on all
    6,252 live rows, is a semicolon-separated list of `City, Region, Country`
    entries, optionally ending in a bare `Remote`:

        'San Francisco, CA, USA'
        'San Francisco, CA, USA; Mountain View, CA, USA'
        'New York City, NY, USA; New York, NY, USA; Remote'
        'Singapore, Singapore'
        'Remote'

    The first entry is taken as the primary location. Anything that yields no
    real geography returns (None, None) rather than a guess: 154 live rows
    are empty strings and 44 are a bare 'Remote', and 'Remote' as a country
    would be worse than no country. Where a location has no city segment of
    its own (`'Singapore, Singapore'`), city is left None rather than
    repeating the country name, which is 203 live rows.
    """
    if not all_locations:
        return None, None
    first = all_locations.split(";")[0].strip()
    if not first or first == "Remote":
        return None, None
    parts = [part.strip() for part in first.split(",")]
    country = parts[-1] or None
    if country == "Remote":
        return None, None
    city = parts[0] or None
    if city == country:
        city = None
    return city, country


def write_company(
    repository: CompanyRepositoryPort, domain: str, new_values: dict
) -> None:
    """Read the current gold.company row for `domain` (None on first
    occurrence), apply `new_values` via apply_company_update, and write
    the result back. See ADR-0002 and `huginn.elt.gold.dimensional` for
    the Type 1/Type 2 history rule this wires to Postgres.

    A key that is absent from `new_values` is not written; a key whose
    value is None IS written, and NULLs the column. The caller owns that
    distinction, and `CompanyWriter.write_all` gets it right by never
    putting a None value in the dict in the first place. A caller that
    assembles `new_values` by hand must do the same: `{"country": None}`
    erases a known country, whereas omitting the key leaves it alone.
    `build_upsert_query` filters on key presence, not on value, so it
    cannot make that choice for you.

    Must be called from inside `with repository:` (see
    `CompanyWriter.write_all`); this function opens no connection of its
    own.
    """
    current = repository.get_company(domain)
    result = apply_company_update(current or {}, new_values)

    # No history on first occurrence: apply_company_update can't tell "no
    # row" from "row exists but the field was never set" (current.get(...)
    # reads None either way), and there's no prior version to supersede
    # when current is None. Acting on it would insert a company_history
    # row with company_id = NULL (current.get("id") on an empty dict),
    # violating that column's NOT NULL constraint.
    should_write_history = current is not None and result.history_snapshot is not None
    repository.upsert_company(
        domain, result.new_values, bump_current_since=should_write_history
    )

    if should_write_history:
        snapshot = result.history_snapshot
        repository.insert_history(
            company_id=snapshot["company_id"],
            domain=domain,
            snapshot=snapshot,
            valid_from=current["current_since"],
        )


class CompanyWriter:
    """Reads every domain-normalized silver.resolved_signals row and
    upserts gold.company via `write_company`. Jira KAN-40.

    Only domain-normalized rows: a placeholder key awaiting manual review
    (`huginn.elt.silver.resolution.KeyDerivation.UNRESOLVED`) is
    not a real company identity yet (architecture document section 6), so
    writing it into Company would put a synthetic "unresolved:..." value
    where the durable natural key belongs. Enforced by
    `CompanyRepositoryPort.read_domain_normalized_signals`'s own query, not
    here.

    Only `domain`, `name`, `stage`, `company_status`, `company_scale`,
    `business_sector`, `country`, `city`, and `yc_batch` are derivable from
    resolved_signals today: docs/entities.md's ResolvedSignal carries no
    team_composition_signal, icp_filter_pass, or contact field. Those stay at
    their gold.company default until a future writer (Jira KAN-43, enrichment)
    has real data for them and calls `write_company` with a richer
    `new_values` dict.

    Two of the derivable ones are not read from resolved_signals directly.
    `company_scale` comes from YC's raw `team_size` integer, bucketed into
    the four constrained bands here, because the bands are Huginn's
    vocabulary rather than a source's (see team_size_to_scale).
    `country` and `city` come from YC's `all_locations` display string,
    split here for the same reason (see parse_all_locations). `yc_batch` is
    YC's own funded-batch label carried through unchanged, but under a
    Huginn-prefixed column name so the column stays unambiguous about which
    portal assigned it.
    """

    def __init__(self, repository: CompanyRepositoryPort) -> None:
        self._repository = repository

    def write_all(self) -> int:
        """Upsert every distinct company found among domain-normalized
        signals, returning the count of companies written.

        `read_domain_normalized_signals` returns event grain (one row per
        original signal, per docs/entities.md's ResolvedSignal); the same
        domain can appear many times. Collapsing to one write per domain
        here saves the redundant read/write round-trips a company with N
        signals would otherwise cost, at no loss: gold.company only ever
        holds current state (ADR-0002), so only one name would have
        survived anyway.

        The collapse is per field, not per row. `name` keeps plain
        last-read-wins, unchanged, because it is NOT NULL upstream and
        every signal carries one. `stage`, `company_status`, `business_sector`,
        `country`, `city`, `yc_batch`, and the `company_scale` derived from
        `team_size` keep the last *non-null* value instead, because they are
        source-specific: every HN signal has all of them as None by
        construction (silver/hn_staging.py), so a plain last-row-wins collapse
        erases a YC company's values whenever an HN signal for the same
        domain is read after it. Absence means "this source does not know",
        not "no value".

        A field absent from every signal is omitted from `new_values`
        entirely, so gold.company keeps whatever an earlier run wrote
        rather than being reset to NULL. Which columns are mergeable this
        way and which instead need a null to clear them (icp_filter_pass,
        per architecture document section 4.3) is the open column
        classification in Jira KAN-20.
        """
        with self._repository:
            signals = self._repository.read_domain_normalized_signals()
            values_by_domain: dict[str, dict[str, object]] = {}
            for signal in signals:
                values = values_by_domain.setdefault(signal.domain, {})
                values["name"] = signal.company_name_raw
                city, country = parse_all_locations(signal.all_locations)
                for column, value in (
                    ("stage", signal.stage),
                    ("company_status", signal.company_status),
                    ("company_scale", team_size_to_scale(signal.team_size)),
                    (
                        "business_sector",
                        list(signal.industries)
                        if signal.industries is not None
                        else None,
                    ),
                    ("country", country),
                    ("city", city),
                    ("yc_batch", signal.batch),
                ):
                    if value is not None:
                        values[column] = value
            for domain, new_values in values_by_domain.items():
                write_company(self._repository, domain, new_values)
            written = len(values_by_domain)

        logger.info("gold.company write_all: %d written", written)
        return written
