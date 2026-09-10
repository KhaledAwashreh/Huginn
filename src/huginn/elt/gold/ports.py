"""Port contract for the Gold Company/CompanyHistory writer. See
architecture document section 4.3, ADR-0002, and CLAUDE.md design
standard 6 (ports-and-adapters): `huginn.elt.gold.company` depends only on
this Protocol, never `psycopg` directly; the concrete Postgres class lives
in `huginn.elt.gold.repositories`.

One port covering every read and write the writer needs, matching the
per-orchestrator port shape already used in `huginn.elt.silver.ports` and
`huginn.elt.bronze.ports`: a context manager scoping one connection and
one transaction to the whole batch, not to each individual statement.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from huginn.elt.gold.models import DomainNormalizedSignal


class CompanyRepositoryPort(Protocol):
    def __enter__(self) -> CompanyRepositoryPort:
        """Acquire whatever the statements below need, and return the
        object those statements are then called on.
        """
        ...

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Release what `__enter__` acquired, committing the block's work
        on a clean exit and discarding it if the block raised.

        Must not suppress the exception: return None, never a truthy value.
        """
        ...

    def read_domain_normalized_signals(self) -> list[DomainNormalizedSignal]:
        """Every silver.resolved_signals row with
        key_derivation = 'domain_normalized'. A placeholder key
        (unresolved) is not a company identity yet and is never
        returned here; see `huginn.elt.gold.models.DomainNormalizedSignal`.
        """
        ...

    def get_company(self, domain: str) -> dict | None:
        """The current gold.company row for `domain`, or None if no row
        exists yet (first occurrence).

        Only the fields `apply_company_update` needs are guaranteed:
        "id", "current_since", and the three
        `huginn.elt.gold.dimensional.TYPE_2_TRACKED_FIELDS`
        ("business_sector", "team_composition_signal", "icp_filter_pass").
        A caller wanting another gold.company column's current value must
        extend both this method's contract and its Postgres implementation
        (`huginn.elt.gold.repositories.company_repository`), not assume
        every column is already present.
        """
        ...

    def upsert_company(
        self, domain: str, new_values: dict, bump_current_since: bool
    ) -> None:
        """Insert `domain` as a new company, or update an existing one's
        columns named in `new_values`. `domain` is always written from
        this parameter, never from a "domain" key inside `new_values`
        (there is no need to duplicate it there). `bump_current_since` is
        True only when a Type 2 tracked field actually changed on an
        existing row (ADR-0002: `current_since` marks when the current
        Type 2 value set took effect).
        """
        ...

    def insert_history(
        self,
        company_id: str,
        domain: str,
        snapshot: dict,
        valid_from: datetime,
    ) -> None:
        """Insert one gold.company_history row for the version `snapshot`
        (a `CompanyUpdate.history_snapshot`, see
        `huginn.elt.gold.dimensional`), superseded from `valid_from` up to
        the moment of this write. The end of that window is the
        database's own clock (Postgres `now()`), not a timestamp computed
        by the caller: it must match the same `now()` that `upsert_company`
        used to set the row's new `current_since` in this same
        transaction, and Postgres's `now()` is transaction-stable, so
        reusing it here rather than a fresh Python-side timestamp is what
        keeps the two boundaries as one instant instead of two clocks.
        """
        ...
