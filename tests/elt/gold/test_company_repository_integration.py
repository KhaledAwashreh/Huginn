"""Live-Postgres integration coverage for
`PostgresCompanyRepository.read_unenriched_company_names`.

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
The fake-repository unit tests elsewhere (e.g. test_company.py) can't
verify real SQL execution against gold.company (column names, the
`business_sector IS NULL` filter, `created_at` ordering, the `LIMIT`
bind); this is that verification. See
architecture-notes/opencorporates-fetch-plan.md section 5.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository

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


def _insert_company(
    cur, domain: str, name: str, business_sector: str | None, created_at: datetime
) -> None:
    """Insert one isolated company fixture through the supplied cursor."""
    cur.execute(
        """
        INSERT INTO gold.company (domain, name, business_sector, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (domain, name, business_sector, created_at),
    )


def test_read_unenriched_company_names_returns_only_rows_with_null_business_sector():
    """Candidate reads exclude companies that already have a sector."""
    suffix = str(uuid.uuid4().int)[:10]
    unenriched_domain = f"opencorptest-unenriched-{suffix}.example"
    enriched_domain = f"opencorptest-enriched-{suffix}.example"
    now = datetime.now(UTC)

    try:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            _insert_company(cur, unenriched_domain, "UnenrichedCo", None, now)
            _insert_company(cur, enriched_domain, "EnrichedCo", "software", now)

        with PostgresCompanyRepository(DATABASE_URL) as repository:
            names = repository.read_unenriched_company_names(limit=1000)

        assert "UnenrichedCo" in names
        assert "EnrichedCo" not in names
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain IN (%s, %s)",
                (unenriched_domain, enriched_domain),
            )


def test_read_unenriched_company_names_orders_oldest_created_first():
    """Candidate reads prioritize the oldest company row."""
    suffix = str(uuid.uuid4().int)[:10]
    older_domain = f"opencorptest-older-{suffix}.example"
    newer_domain = f"opencorptest-newer-{suffix}.example"
    older = datetime.now(UTC) - timedelta(days=2)
    newer = datetime.now(UTC) - timedelta(days=1)

    try:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            # Insert newer row first so a correct ORDER BY, not insertion
            # order, is what the assertion below actually exercises.
            _insert_company(cur, newer_domain, "NewerCo", None, newer)
            _insert_company(cur, older_domain, "OlderCo", None, older)

        with PostgresCompanyRepository(DATABASE_URL) as repository:
            names = repository.read_unenriched_company_names(limit=1000)

        assert names.index("OlderCo") < names.index("NewerCo")
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain IN (%s, %s)",
                (older_domain, newer_domain),
            )


def test_read_unenriched_company_names_respects_the_limit():
    """Candidate reads never exceed the caller's requested limit."""
    suffix = str(uuid.uuid4().int)[:10]
    domains = [f"opencorptest-limit-{suffix}-{i}.example" for i in range(3)]
    now = datetime.now(UTC)

    try:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            for i, domain in enumerate(domains):
                _insert_company(
                    cur, domain, f"LimitCo{i}", None, now + timedelta(seconds=i)
                )

        with PostgresCompanyRepository(DATABASE_URL) as repository:
            names = repository.read_unenriched_company_names(limit=2)

        assert len(names) <= 2
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain = ANY(%s)",
                (domains,),
            )
