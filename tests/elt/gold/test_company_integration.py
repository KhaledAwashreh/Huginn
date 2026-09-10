"""Live-Postgres integration coverage for CompanyWriter.

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from huginn.elt.gold.company import CompanyWriter
from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository

DATABASE_URL = os.environ.get("HUGINN_DATABASE_URL")


def _database_reachable() -> bool:
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


def _insert_resolved_signal(cur, source_stable_id: str, domain: str) -> None:
    cur.execute(
        """
        INSERT INTO silver.resolved_signals
            (source_stable_id, source, resolved_company_key, company_name_raw,
             signal_type, occurred_on, url, match_confidence)
        VALUES (%s, 'hn', %s, %s, 'hiring', %s, %s, 'auto_matched')
        """,
        (
            source_stable_id,
            domain,
            "CompanyWriterTestCo",
            datetime.now(UTC),
            "https://example.invalid",
        ),
    )


def test_write_all_creates_a_new_company_from_an_auto_matched_signal():
    stable_id = str(uuid.uuid4().int)[:10]
    domain = f"companywritertest-{stable_id}.example"
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        _insert_resolved_signal(cur, stable_id, domain)

    try:
        written = CompanyWriter(PostgresCompanyRepository(DATABASE_URL)).write_all()

        assert written >= 1

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT name, team_composition_signal, icp_filter_pass "
                "FROM gold.company WHERE domain = %s",
                (domain,),
            )
            name, team_composition_signal, icp_filter_pass = cur.fetchone()

        assert name == "CompanyWriterTestCo"
        assert team_composition_signal == "unknown"
        assert icp_filter_pass is False

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM gold.company_history WHERE domain = %s",
                (domain,),
            )
            (history_count,) = cur.fetchone()

        assert history_count == 0
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source_stable_id = %s "
                "AND source = 'hn'",
                (stable_id,),
            )
            cur.execute("DELETE FROM gold.company_history WHERE domain = %s", (domain,))
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))


def test_write_all_updates_an_existing_companys_name_without_writing_history():
    stable_id = str(uuid.uuid4().int)[:10]
    domain = f"companywritertest-{stable_id}.example"
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.company (domain, name) VALUES (%s, 'Old Name')",
            (domain,),
        )
        _insert_resolved_signal(cur, stable_id, domain)

    try:
        CompanyWriter(PostgresCompanyRepository(DATABASE_URL)).write_all()

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT name FROM gold.company WHERE domain = %s", (domain,))
            (name,) = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM gold.company_history WHERE domain = %s",
                (domain,),
            )
            (history_count,) = cur.fetchone()

        assert name == "CompanyWriterTestCo"
        assert history_count == 0
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source_stable_id = %s "
                "AND source = 'hn'",
                (stable_id,),
            )
            cur.execute("DELETE FROM gold.company_history WHERE domain = %s", (domain,))
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))


def test_write_all_breaks_resolved_at_ties_deterministically_by_id():
    """Regression: resolved_at defaults to Postgres's transaction-stable
    now(), so two rows inserted together share the exact same value.
    Without a secondary ORDER BY key, which one wins CompanyWriter's
    domain collapse is undefined; ordering by id afterward makes it
    deterministic and repeatable across runs.
    """
    stable_id_a = str(uuid.uuid4().int)[:10]
    stable_id_b = str(uuid.uuid4().int)[:10]
    domain = f"companywritertest-{stable_id_a}.example"
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO silver.resolved_signals
                (source_stable_id, source, resolved_company_key, company_name_raw,
                 signal_type, occurred_on, url, match_confidence)
            VALUES
                (%s, 'hn', %s, 'First', 'hiring', %s, %s, 'auto_matched'),
                (%s, 'hn', %s, 'Second', 'hiring', %s, %s, 'auto_matched')
            """,
            (
                stable_id_a,
                domain,
                datetime.now(UTC),
                "https://example.invalid",
                stable_id_b,
                domain,
                datetime.now(UTC),
                "https://example.invalid",
            ),
        )
        cur.execute(
            "SELECT company_name_raw FROM silver.resolved_signals "
            "WHERE source_stable_id IN (%s, %s) AND source = 'hn' ORDER BY id",
            (stable_id_a, stable_id_b),
        )
        expected_name = cur.fetchall()[-1][0]

    try:
        CompanyWriter(PostgresCompanyRepository(DATABASE_URL)).write_all()

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT name FROM gold.company WHERE domain = %s", (domain,))
            (name,) = cur.fetchone()

        assert name == expected_name
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source_stable_id IN (%s, %s) "
                "AND source = 'hn'",
                (stable_id_a, stable_id_b),
            )
            cur.execute("DELETE FROM gold.company_history WHERE domain = %s", (domain,))
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))


def test_write_all_ignores_a_placeholder_key_awaiting_manual_review():
    stable_id = str(uuid.uuid4().int)[:10]
    placeholder_key = f"unresolved:hn:{stable_id}"
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO silver.resolved_signals
                (source_stable_id, source, resolved_company_key, company_name_raw,
                 signal_type, occurred_on, url, match_confidence)
            VALUES (%s, 'hn', %s, 'UnmatchedCo', 'hiring', %s, %s, 'no_existing_match')
            """,
            (
                stable_id,
                placeholder_key,
                datetime.now(UTC),
                "https://example.invalid",
            ),
        )

    try:
        CompanyWriter(PostgresCompanyRepository(DATABASE_URL)).write_all()

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM gold.company WHERE domain = %s",
                (placeholder_key,),
            )
            (count,) = cur.fetchone()

        assert count == 0
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source_stable_id = %s "
                "AND source = 'hn'",
                (stable_id,),
            )
