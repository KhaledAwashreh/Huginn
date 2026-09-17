"""Postgres `CompanySignalRepositoryPort` implementation: the only module
holding gold.company_signal SQL and the only one that opens a connection
to run it. See huginn.elt.gold.ports, huginn.elt.gold.company_signal (the
writer this persists for), db/schema/gold.sql, and ADR-0007 (the
(source, source_stable_id) idempotency key and ON CONFLICT design this
module implements).
"""

from __future__ import annotations

import psycopg

from huginn.elt.gold.models import ResolvedSignalForFact

# Only domain-normalized signals carry a durable domain key that can match
# a gold.company row (architecture document section 6); the inner join
# itself enforces this, not application code re-checking key_derivation
# (this plan's Global Constraint 1).
_READ_SIGNAL_FACTS_SQL = """
    SELECT c.id, rs.source, rs.source_stable_id, rs.signal_type, rs.url,
           rs.stage, rs.description, rs.occurred_on
    FROM silver.resolved_signals rs
    JOIN gold.company c ON c.domain = rs.resolved_company_key
    WHERE rs.key_derivation = 'domain_normalized'
"""

_UPSERT_SIGNAL_SQL = """
    INSERT INTO gold.company_signal
        (company_id, source, source_stable_id, signal_type, source_url, stage, description, occurred_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (source, source_stable_id) DO UPDATE SET
        company_id = EXCLUDED.company_id,
        signal_type = EXCLUDED.signal_type,
        source_url = EXCLUDED.source_url,
        stage = EXCLUDED.stage,
        description = EXCLUDED.description,
        occurred_at = EXCLUDED.occurred_at
"""


def build_read_signal_facts_query() -> tuple[str, tuple]:
    """Parameterized query for `CompanySignalRepositoryPort.read_signal_facts`.
    A function even though it takes no parameters, matching
    `build_read_unenriched_company_names_query`'s shape in
    `company_repository.py` for consistency and test symmetry.
    """
    return _READ_SIGNAL_FACTS_SQL, ()


def build_upsert_signal_query(fact: ResolvedSignalForFact) -> tuple[str, tuple]:
    """Parameterized upsert on (source, source_stable_id), per ADR-0007.
    `id` and `ingested_at` are never in the `DO UPDATE SET` list: `id` is
    generated once, and `ingested_at` keeps its first-insert value forever,
    matching `gold.company.created_at`'s precedent in
    `company_repository.build_upsert_query`. Bind parameters only, never
    string-built SQL (BEST_PRACTICES.md section 8.1).
    """
    params = (
        fact.company_id,
        fact.source,
        fact.source_stable_id,
        fact.signal_type,
        fact.source_url,
        fact.stage,
        fact.description,
        fact.occurred_at,
    )
    return _UPSERT_SIGNAL_SQL, params


class PostgresCompanySignalRepository:
    """`CompanySignalRepositoryPort` implementation against
    gold.company_signal.

    A context manager: one connection and one cursor span the whole `with`
    block, so `CompanySignalWriter.write_all()`'s entire batch shares a
    single connection and a single transaction (this plan's Global
    Constraint 5), matching `PostgresCompanyRepository`'s own connection
    lifecycle rather than Silver's shared `PostgresConnectionScope`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresCompanySignalRepository:
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

    def read_signal_facts(self) -> list[ResolvedSignalForFact]:
        """Implement `CompanySignalRepositoryPort.read_signal_facts`."""
        self._cur.execute(*build_read_signal_facts_query())
        return [
            ResolvedSignalForFact(
                company_id=row[0],
                source=row[1],
                source_stable_id=row[2],
                signal_type=row[3],
                source_url=row[4],
                stage=row[5],
                description=row[6],
                occurred_at=row[7],
            )
            for row in self._cur.fetchall()
        ]

    def upsert_signal(self, fact: ResolvedSignalForFact) -> None:
        """Implement `CompanySignalRepositoryPort.upsert_signal`."""
        self._cur.execute(*build_upsert_signal_query(fact))
