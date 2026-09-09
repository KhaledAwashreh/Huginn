"""Live-Postgres integration coverage for SignalResolver.

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from huginn.elt.silver.repositories.signal_resolution_repository import (
    PostgresSignalResolutionRepository,
)
from huginn.elt.silver.signal_resolution import SignalResolver

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


def _insert_hn_posting(cur, stable_id: str, website: str | None) -> None:
    cur.execute(
        """
        INSERT INTO silver.hn_postings
            (stable_id, company_name_raw, website, signal_type, occurred_on, url)
        VALUES (%s, %s, %s, 'hiring', %s, %s)
        """,
        (
            stable_id,
            "ResolutionTestCo",
            website,
            datetime.now(UTC),
            "https://example.invalid",
        ),
    )


def test_resolve_all_auto_matches_a_row_with_a_website():
    stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        _insert_hn_posting(cur, stable_id, "https://www.resolutiontestco.example")

    try:
        resolver = SignalResolver(PostgresSignalResolutionRepository(DATABASE_URL))
        written = resolver.resolve_all()

        assert written >= 1

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT resolved_company_key, match_confidence FROM silver.resolved_signals "
                "WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            key, confidence = cur.fetchone()

        assert key == "resolutiontestco.example"
        assert confidence == "auto_matched"
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = %s", (stable_id,)
            )


def test_resolve_all_marks_no_existing_match_when_website_is_none():
    stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        _insert_hn_posting(cur, stable_id, None)

    try:
        SignalResolver(PostgresSignalResolutionRepository(DATABASE_URL)).resolve_all()

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT resolved_company_key, match_confidence FROM silver.resolved_signals "
                "WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            key, confidence = cur.fetchone()

        assert key == f"unresolved:hn:{stable_id}"
        assert confidence == "no_existing_match"
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = %s", (stable_id,)
            )
