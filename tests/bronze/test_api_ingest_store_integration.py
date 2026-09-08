"""Live-Postgres integration coverage for PostgresApiIngestStore.write().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
See docs/superpowers/plans/2026-09-08-kan-32-raw-store-port.md Task 4 and
Global Constraint 8: the fake-cursor unit tests in test_api_ingest_store.py
cannot verify real SQL execution against bronze.api_ingest (column names,
the ON CONFLICT target, the ::uuid cast, JSONB round-tripping). This test
is that verification, gated on a real database actually being present.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.ingestion.ports import RawRecord

DATABASE_URL = os.environ.get("HUGINN_DATABASE_URL")


def _database_reachable() -> bool:
    if not DATABASE_URL:
        return False
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(),
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable; see plan Task 4",
)


def test_write_then_write_again_with_same_payload_only_touches_last_checked_at():
    store = PostgresApiIngestStore(DATABASE_URL)
    source = "kan32-integration-test"
    stable_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    payload = {"title": "Integration Test Posting"}
    record = [RawRecord(stable_id=stable_id, payload=payload)]

    try:
        store.write(source, "api", record, run_id)
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, fetched_at FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            first_hash, first_fetched_at = cur.fetchone()

        store.write(source, "api", record, str(uuid.uuid4()))
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, fetched_at, last_checked_at FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            second_hash, second_fetched_at, last_checked_at = cur.fetchone()

        assert second_hash == first_hash
        assert second_fetched_at == first_fetched_at
        assert last_checked_at >= first_fetched_at
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
