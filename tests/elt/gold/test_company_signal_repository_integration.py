"""Live-Postgres integration coverage for
`PostgresCompanySignalRepository`.

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
The fake-repository unit tests elsewhere (test_company_signal_repository.py)
can't verify real SQL execution against gold.company_signal and the join
against gold.company (column names, the key_derivation filter, the
(source, source_stable_id) ON CONFLICT upsert); this is that verification.
See ADR-0007.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from huginn.elt.gold.models import ResolvedSignalForFact
from huginn.elt.gold.repositories.company_signal_repository import (
    PostgresCompanySignalRepository,
)

DATABASE_URL = os.environ.get("HUGINN_DATABASE_URL")


def _database_reachable() -> bool:
    """Return whether the configured integration database accepts a query."""
    if not DATABASE_URL:
        return False
    try:
        with (
            psycopg.connect(DATABASE_URL, connect_timeout=2) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(),
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable",
)


def _insert_company(cur, domain: str, name: str) -> str:
    """Insert one isolated gold.company fixture, returning its id."""
    cur.execute(
        """
        INSERT INTO gold.company (domain, name)
        VALUES (%s, %s)
        RETURNING id
        """,
        (domain, name),
    )
    return cur.fetchone()[0]


def _insert_resolved_signal(
    cur,
    source: str,
    source_stable_id: str,
    resolved_company_key: str,
    description: str,
) -> None:
    """Insert one isolated silver.resolved_signals fixture, domain-normalized."""
    cur.execute(
        """
        INSERT INTO silver.resolved_signals
            (source, source_stable_id, resolved_company_key, company_name_raw,
             signal_type, stage, description, occurred_on, url, key_derivation)
        VALUES (%s, %s, %s, %s, 'hiring', NULL, %s, %s, %s, 'domain_normalized')
        """,
        (
            source,
            source_stable_id,
            resolved_company_key,
            "Acme",
            description,
            datetime(2026, 1, 1, tzinfo=UTC),
            "https://example.invalid",
        ),
    )


def test_read_and_upsert_signal_facts_round_trip():
    """read_signal_facts joins to gold.company correctly, and upsert_signal
    is idempotent on (source, source_stable_id): calling it twice with a
    changed description leaves exactly one row with the latest content.
    """
    suffix = str(uuid.uuid4().int)[:10]
    domain = f"companysignaltest-{suffix}.example"
    source = "hn"
    source_stable_id = f"companysignaltest-{suffix}"

    try:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            company_id = _insert_company(cur, domain, "Acme")
            _insert_resolved_signal(
                cur, source, source_stable_id, domain, "first description"
            )

        with PostgresCompanySignalRepository(DATABASE_URL) as repository:
            facts = repository.read_signal_facts()

        matching = [f for f in facts if f.source_stable_id == source_stable_id]
        assert len(matching) == 1
        fact = matching[0]
        assert fact.company_id == company_id
        assert fact.source == source
        assert fact.signal_type == "hiring"
        assert fact.description == "first description"

        with PostgresCompanySignalRepository(DATABASE_URL) as repository:
            repository.upsert_signal(fact)

        updated_fact = ResolvedSignalForFact(
            company_id=fact.company_id,
            source=fact.source,
            source_stable_id=fact.source_stable_id,
            signal_type=fact.signal_type,
            source_url=fact.source_url,
            stage=fact.stage,
            description="second description",
            occurred_at=fact.occurred_at,
        )
        with PostgresCompanySignalRepository(DATABASE_URL) as repository:
            repository.upsert_signal(updated_fact)

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT description FROM gold.company_signal "
                "WHERE source = %s AND source_stable_id = %s",
                (source, source_stable_id),
            )
            rows = cur.fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "second description"
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company_signal WHERE source = %s AND source_stable_id = %s",
                (source, source_stable_id),
            )
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source = %s AND source_stable_id = %s",
                (source, source_stable_id),
            )
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))
