"""Postgres `CompanyRepositoryPort` implementation: the only module
holding gold.company/gold.company_history SQL and the only one that opens
a connection to run it. See huginn.elt.gold.ports, huginn.elt.gold.company
(the writer this persists for), db/schema/gold.sql, ADR-0002, and
BEST_PRACTICES.md section 8.1 (bind parameters only, never string-built
SQL).

`PostgresCompanyRepository` also implements `EnrichmentCandidatePort`
(structurally, no shared base class): an unrelated read used by
ingestion's wiring, not by `CompanyWriter`. See
architecture-notes/opencorporates-fetch-plan.md section 5.
"""

from __future__ import annotations

from datetime import datetime

import psycopg

from huginn.elt.gold.models import DomainNormalizedSignal

# `id` breaks ties so CompanyWriter.write_all()'s domain-collapse (last row
# read wins) is repeatable rather than dependent on whatever incidental order
# Postgres happens to return same-timestamp rows in. `resolved_at` alone does
# not pin that order: it defaults to a transaction-stable now(), so every row
# one resolve_all() batch writes shares the exact same value, not just
# occasionally. It is set on INSERT and never refreshed by the ON CONFLICT
# path (which updates updated_at), so it records when a signal was first seen.
# With two sources this is stable in practice because a domain has at most
# one non-NULL value per source-shaped field; the secondary key matters once
# a third source can supply competing values for the same field.
_READ_DOMAIN_NORMALIZED_SQL = """
    SELECT resolved_company_key, company_name_raw, stage,
           company_status, team_size, industries, all_locations, batch
    FROM silver.resolved_signals
    WHERE key_derivation = 'domain_normalized'
    ORDER BY resolved_at, id
"""

# FOR UPDATE: locks an existing row for the rest of this transaction, so a
# second write_company() call racing on the same domain (a concurrent
# write_all() run, or a future writer) can't read the same pre-update
# state this one is about to act on.
_GET_COMPANY_SQL = """
    SELECT id, business_sector, team_composition_signal, current_since
    FROM gold.company
    WHERE domain = %s
    FOR UPDATE
"""

_READ_UNENRICHED_COMPANY_NAMES_SQL = """
    SELECT name
    FROM (
        SELECT DISTINCT ON (name) name, created_at, id
        FROM gold.company
        WHERE business_sector IS NULL
        ORDER BY name, created_at, id
    ) AS distinct_companies
    ORDER BY created_at, id
    LIMIT %s
"""

_INSERT_HISTORY_SQL = """
    INSERT INTO gold.company_history
        (company_id, domain, business_sector, team_composition_signal,
         valid_from, valid_to)
    VALUES (%s, %s, %s, %s, %s, now())
"""

# The only gold.company columns a caller may set through upsert_company,
# beyond "domain" itself (always supplied separately, see
# build_upsert_query). `columns` in build_upsert_query is always filtered
# against this fixed, code-controlled tuple before any name reaches SQL
# text, so an unrecognized key in new_values is silently dropped rather
# than ever being interpolated (BEST_PRACTICES.md section 8.1).
_COMPANY_COLUMNS = (
    "name",
    "stage",
    "company_status",
    "business_sector",
    "notes",
    "company_scale",
    "legal_form",
    "country",
    "city",
    "address",
    "phone_number",
    "email",
    "team_composition_signal",
)


def build_read_unenriched_company_names_query(limit: int) -> tuple[str, tuple[int]]:
    """Parameterized query for `EnrichmentCandidatePort.read_unenriched_company_names`:
    up to `limit` distinct gold.company names with `business_sector IS NULL`,
    oldest-created first with `id` as the deterministic tie-breaker
    (architecture-notes/opencorporates-fetch-plan.md section 5). `limit` is
    always a bind parameter, never interpolated into the SQL text
    (BEST_PRACTICES.md section 8.1).
    """
    return _READ_UNENRICHED_COMPANY_NAMES_SQL, (limit,)


def _with_timestamp_assignments(assignments: str, bump_current_since: bool) -> str:
    """Append the two timestamps both write shapes move: `current_since`
    only when asked, `updated_at` always.
    """
    parts = [assignments] if assignments else []
    if bump_current_since:
        parts.append("current_since = now()")
    parts.append("updated_at = now()")
    return ", ".join(parts)


def build_upsert_query(
    domain: str, new_values: dict, bump_current_since: bool
) -> tuple[str, tuple]:
    """Parameterized write over "domain" plus whichever `_COMPANY_COLUMNS`
    are present in `new_values`, in one of two shapes, chosen by whether
    "name" is a key (ADR-0009, which records why a single statement cannot
    cover both).

    With "name", one `INSERT ... ON CONFLICT (domain) DO UPDATE`: a new domain
    is inserted, an existing one updated in place, with no preceding read.
    Without it, `UPDATE ... WHERE domain = %s`, which sets only columns the
    caller supplied and never attempts an insert.

    `domain` always comes from this parameter, never from a "domain" key
    inside `new_values`, in either shape, so no caller string reaches the
    ON CONFLICT target or the WHERE clause. `bump_current_since` moves
    `current_since` only when asked; a fresh `INSERT` already gets
    `current_since = now()` from the column default regardless (see
    db/schema/gold.sql), so it is never observable on insert.
    """
    columns = [column for column in _COMPANY_COLUMNS if column in new_values]

    if "name" in new_values:
        insert_columns = ["domain", *columns]
        update_set = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns)
        sql = (
            f"INSERT INTO gold.company ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(['%s'] * len(insert_columns))}) "
            "ON CONFLICT (domain) DO UPDATE SET "
            f"{_with_timestamp_assignments(update_set, bump_current_since)}"
        )
        return sql, (domain, *(new_values[column] for column in columns))

    update_set = ", ".join(f"{column} = %s" for column in columns)
    sql = (
        "UPDATE gold.company "
        f"SET {_with_timestamp_assignments(update_set, bump_current_since)} "
        "WHERE domain = %s"
    )
    return sql, (*(new_values[column] for column in columns), domain)


class PostgresCompanyRepository:
    """`CompanyRepositoryPort` implementation against gold.company and
    gold.company_history.

    A context manager: one connection and one cursor span the whole
    `with` block, so `CompanyWriter.write_all()`'s entire batch shares a
    single connection and a single transaction, matching the connection-
    per-call pattern already used in
    `huginn.elt.bronze.repositories.api_ingest_repository` and
    `huginn.elt.silver.repositories.postgres_repository`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresCompanyRepository:
        """Open the connection and cursor this block's statements share.

        If opening the cursor fails, the connection is closed before the
        exception propagates: `__exit__` never runs when `__enter__`
        itself raises (the `with` protocol), so this is the only chance
        to avoid leaking the already-open connection.
        """
        self._conn = psycopg.connect(self._database_url)
        try:
            self._cur = self._conn.cursor()
        except Exception:
            self._conn.close()
            self._conn = None
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if self._cur is not None:
                self._cur.close()
            if self._conn is not None:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            if self._conn is not None:
                self._conn.close()
            self._cur = None
            self._conn = None
        return None

    def read_domain_normalized_signals(self) -> list[DomainNormalizedSignal]:
        """Implement `CompanyRepositoryPort.read_domain_normalized_signals`."""
        self._cur.execute(_READ_DOMAIN_NORMALIZED_SQL)
        return [
            DomainNormalizedSignal(
                domain=row[0],
                company_name_raw=row[1],
                stage=row[2],
                company_status=row[3],
                team_size=row[4],
                industries=list(row[5]) if row[5] is not None else None,
                all_locations=row[6],
                batch=row[7],
            )
            for row in self._cur.fetchall()
        ]

    def read_unenriched_company_names(self, limit: int) -> list[str]:
        """Implement `EnrichmentCandidatePort.read_unenriched_company_names`."""
        self._cur.execute(*build_read_unenriched_company_names_query(limit))
        return [row[0] for row in self._cur.fetchall()]

    def get_company(self, domain: str) -> dict | None:
        self._cur.execute(_GET_COMPANY_SQL, (domain,))
        row = self._cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "business_sector": row[1],
            "team_composition_signal": row[2],
            "current_since": row[3],
        }

    def upsert_company(
        self, domain: str, new_values: dict, bump_current_since: bool
    ) -> None:
        """Implement `CompanyRepositoryPort.upsert_company`.

        A write carrying no "name" is update-only (see build_upsert_query),
        so a domain with no row matches nothing and no company is created.
        That is a fact about the call rather than about the data: there is
        no name to insert. Raised here, where the rowcount is known, so it
        cannot be mistaken for a write that happened.
        """
        self._cur.execute(*build_upsert_query(domain, new_values, bump_current_since))
        if "name" not in new_values and self._cur.rowcount == 0:
            raise ValueError(
                f"no gold.company row for {domain}, and new_values has no 'name' to "
                "create one with. Supply 'name' to insert a new company, or only "
                "write companies that already exist."
            )

    def insert_history(
        self,
        company_id: str,
        domain: str,
        snapshot: dict,
        valid_from: datetime,
    ) -> None:
        self._cur.execute(
            _INSERT_HISTORY_SQL,
            (
                company_id,
                domain,
                snapshot["business_sector"],
                snapshot["team_composition_signal"],
                valid_from,
            ),
        )
