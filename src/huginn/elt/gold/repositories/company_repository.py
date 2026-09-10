"""Postgres `CompanyRepositoryPort` implementation: the only module
holding gold.company/gold.company_history SQL and the only one that opens
a connection to run it. See huginn.elt.gold.ports, huginn.elt.gold.company
(the writer this persists for), db/schema/gold.sql, ADR-0002, and
BEST_PRACTICES.md section 8.1 (bind parameters only, never string-built
SQL).
"""

from __future__ import annotations

from datetime import datetime

import psycopg

from huginn.elt.gold.models import DomainNormalizedSignal

# `id` breaks ties deterministically: `resolved_at` defaults to Postgres's
# transaction-stable now(), so every row silver.resolve_all() writes in one
# batch shares the exact same value, not just occasionally. Without a
# secondary key, CompanyWriter.write_all()'s domain-collapse (last row
# read wins) would depend on whatever incidental order Postgres happens to
# return same-timestamp rows in.
_READ_DOMAIN_NORMALIZED_SQL = """
    SELECT resolved_company_key, company_name_raw
    FROM silver.resolved_signals
    WHERE key_derivation = 'domain_normalized'
    ORDER BY resolved_at, id
"""

# FOR UPDATE: locks an existing row for the rest of this transaction, so a
# second write_company() call racing on the same domain (a concurrent
# write_all() run, or a future writer) can't read the same pre-update
# state this one is about to act on.
_GET_COMPANY_SQL = """
    SELECT id, business_sector, team_composition_signal, icp_filter_pass,
           current_since
    FROM gold.company
    WHERE domain = %s
    FOR UPDATE
"""

_INSERT_HISTORY_SQL = """
    INSERT INTO gold.company_history
        (company_id, domain, business_sector, team_composition_signal,
         icp_filter_pass, valid_from, valid_to)
    VALUES (%s, %s, %s, %s, %s, %s, now())
"""

# The only gold.company columns a caller may set through upsert_company,
# beyond "domain" itself (always supplied separately, see
# build_upsert_query). `columns` in build_upsert_query is always filtered
# against this fixed, code-controlled tuple before any name reaches SQL
# text, so an unrecognized key in new_values is silently dropped rather
# than ever being interpolated (BEST_PRACTICES.md section 8.1).
_COMPANY_COLUMNS = (
    "name",
    "business_sector",
    "company_type",
    "country",
    "city",
    "address",
    "phone_number",
    "email",
    "team_composition_signal",
    "icp_filter_pass",
)


def build_upsert_query(
    domain: str, new_values: dict, bump_current_since: bool
) -> tuple[str, tuple]:
    """Parameterized upsert over "domain" plus whichever `_COMPANY_COLUMNS`
    are present in `new_values`. `domain` always comes from this
    parameter, never from a "domain" key inside `new_values`: it is both
    the `ON CONFLICT` target and a NOT NULL column, so a caller that
    forgot to duplicate it there must never silently produce an INSERT
    missing it (Postgres validates NOT NULL before ON CONFLICT is even
    considered, so that INSERT fails even when only the UPDATE branch
    should have run). `bump_current_since` bumps `current_since` on the
    `ON CONFLICT` (update) branch only; a fresh `INSERT` already gets
    `current_since = now()` from the column default regardless (see
    db/schema/gold.sql), so `bump_current_since` changing only that
    branch's SQL text is never observable on insert.
    """
    columns = ["domain"] + [
        column for column in _COMPANY_COLUMNS if column in new_values
    ]
    value_placeholders = ", ".join(["%s"] * len(columns))
    update_set = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column != "domain"
    )
    if bump_current_since:
        update_set = (
            f"{update_set}, current_since = now()"
            if update_set
            else "current_since = now()"
        )
    update_set = (
        f"{update_set}, updated_at = now()" if update_set else "updated_at = now()"
    )

    sql = (
        f"INSERT INTO gold.company ({', '.join(columns)}) "
        f"VALUES ({value_placeholders}) "
        f"ON CONFLICT (domain) DO UPDATE SET {update_set}"
    )
    params = (domain, *(new_values[column] for column in columns[1:]))
    return sql, params


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
            DomainNormalizedSignal(domain=row[0], company_name_raw=row[1])
            for row in self._cur.fetchall()
        ]

    def get_company(self, domain: str) -> dict | None:
        self._cur.execute(_GET_COMPANY_SQL, (domain,))
        row = self._cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "business_sector": row[1],
            "team_composition_signal": row[2],
            "icp_filter_pass": row[3],
            "current_since": row[4],
        }

    def upsert_company(
        self, domain: str, new_values: dict, bump_current_since: bool
    ) -> None:
        self._cur.execute(*build_upsert_query(domain, new_values, bump_current_since))

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
                snapshot["icp_filter_pass"],
                valid_from,
            ),
        )
