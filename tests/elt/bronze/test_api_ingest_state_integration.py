"""Live-Postgres integration coverage for PostgresApiIngestState.last_hash().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
See docs/superpowers/plans/2026-09-08-kan-33-state-port.md Task 2 and
Global Constraint 6: the fake-cursor unit tests in
test_api_ingest_state.py cannot verify real SQL execution against
bronze.api_ingest. This test is that verification, gated on a real
database actually being present, matching
tests/bronze/test_api_ingest_store_integration.py's pattern exactly.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.elt.bronze.api_ingest_state import PostgresApiIngestState
from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.ingestion.models import RawRecord

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
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable; see plan Task 2",
)


def test_last_hash_returns_none_for_a_pair_never_written():
    state = PostgresApiIngestState(PostgresApiIngestRepository(DATABASE_URL))
    source = "kan33-integration-test"
    stable_id = str(uuid.uuid4())

    assert state.last_hash(source, stable_id) is None


def test_last_hash_returns_the_hash_a_prior_write_stored():
    repository = PostgresApiIngestRepository(DATABASE_URL)
    store = PostgresApiIngestStore(repository)
    state = PostgresApiIngestState(repository)
    source = "kan33-integration-test"
    stable_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    payload = {"title": "Integration Test Posting"}

    try:
        store.write(
            source, "api", [RawRecord(stable_id=stable_id, payload=payload)], run_id
        )

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            (expected_hash,) = cur.fetchone()

        assert state.last_hash(source, stable_id) == expected_hash
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
