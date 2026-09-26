"""Live-Postgres integration coverage for PostgresApiIngestState.last_hash().

Runs against the throwaway Postgres that tests/conftest.py provisions,
fails rather than skips when testcontainers or Docker is unavailable (tests/conftest.py explains why). See
docs/superpowers/plans/2026-09-08-kan-33-state-port.md Task 2 and
Global Constraint 6: the fake-cursor unit tests in
test_api_ingest_state.py cannot verify real SQL execution against
bronze.api_ingest. This test is that verification, gated on a real
database actually being present, matching
tests/elt/bronze/test_api_ingest_store_integration.py's pattern exactly.
"""

from __future__ import annotations

import uuid

import psycopg

from huginn.elt.bronze.api_ingest_state import PostgresApiIngestState
from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.ingestion.models import RawRecord


def test_last_hash_returns_none_for_a_pair_never_written(
    integration_database_url: str,
):
    state = PostgresApiIngestState(
        PostgresApiIngestRepository(integration_database_url)
    )
    source = "kan33-integration-test"
    stable_id = str(uuid.uuid4())

    assert state.last_hash(source, stable_id) is None


def test_last_hash_returns_the_hash_a_prior_write_stored(
    integration_database_url: str,
):
    repository = PostgresApiIngestRepository(integration_database_url)
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

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            (expected_hash,) = cur.fetchone()

        assert state.last_hash(source, stable_id) == expected_hash
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
