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

from huginn.elt.gold.models import DomainNormalizedSignal, ResolvedSignalForFact


class CompanyRepositoryPort(Protocol):
    """Persistence contract for Gold company writes. See ADR-0002."""

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
        "id", "current_since", and the
        `huginn.elt.gold.dimensional.TYPE_2_TRACKED_FIELDS`
        ("business_sector", "team_composition_signal").
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

        A `new_values` carrying "name" inserts or updates. Without it the
        write is update-only, and raises ValueError if it matched no row,
        rather than reporting a company that was not written (ADR-0009, and
        `huginn.elt.gold.repositories.company_repository.build_upsert_query`).
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


class CompanySignalRepositoryPort(Protocol):
    """Persistence contract for Gold company_signal fact writes. See
    ADR-0007 for the idempotency-key design this port's upsert method
    relies on.
    """

    def __enter__(self) -> CompanySignalRepositoryPort: ...

    def __exit__(self, exc_type, exc_value, traceback) -> None: ...

    def read_signal_facts(self) -> list[ResolvedSignalForFact]:
        """Every domain-normalized silver.resolved_signals row already
        joined to its gold.company row. A row with no matching gold.company
        yet (Company hasn't caught up this run) is not returned; it is
        picked up automatically once Company does, no ordering dependency
        needed between the two writers.
        """
        ...

    def upsert_signal(self, fact: ResolvedSignalForFact) -> None:
        """Insert one gold.company_signal row, or update it in place if
        (source, source_stable_id) already exists (ADR-0007). ingested_at
        is never touched by the update branch.
        """
        ...


class EnrichmentCandidatePort(Protocol):
    """Read contract for selecting gold.company rows still awaiting
    third-party enrichment (e.g. OpenCorporates). Deliberately separate
    from `CompanyRepositoryPort` above: that Protocol is `CompanyWriter`'s
    writes-only contract (see its own docstring), and this read is used by
    ingestion's wiring (`src/huginn/elt/ingestion/__main__.py`), not by
    `CompanyWriter`. Python Protocols are structural, so
    `PostgresCompanyRepository` implements both without inheriting either.
    See architecture-notes/opencorporates-fetch-plan.md section 5.
    """

    def read_unenriched_company_names(self, limit: int) -> list[str]:
        """Up to `limit` gold.company names with `business_sector IS NULL`,
        oldest-created first: never-enriched companies, oldest first,
        capped by the caller's run budget. `business_sector IS NULL`
        doubles as "never successfully enriched yet," with no separate
        enrichment-status column needed (fetch-plan section 5).
        """
        ...

    def read_company_names_pending_eu_startups_search(self, limit: int) -> list[str]:
        """Up to `limit` gold.company names with `eu_startups_searched_at IS NULL`,
        oldest-created first: companies not yet searched via EU-Startups,
        oldest first, capped by the caller's run budget. See ADR-0010.
        """
        ...
