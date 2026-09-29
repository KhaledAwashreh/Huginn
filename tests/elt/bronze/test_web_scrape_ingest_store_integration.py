"""Live-Postgres coverage for web-scrape Bronze persistence."""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.elt.bronze.repositories.web_scrape_ingest_repository import (
    PostgresWebScrapeIngestRepository,
)
from huginn.elt.bronze.web_scrape_ingest_store import PostgresWebScrapeIngestStore
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
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable",
)


def test_insert_touch_and_changed_payload_upsert_round_trip():
    store = PostgresWebScrapeIngestStore(
        PostgresWebScrapeIngestRepository(DATABASE_URL)
    )
    source = "kan83-integration-test"
    stable_id = str(uuid.uuid4())
    payload = {"html": "<main>Brightroom</main>"}
    record = [RawRecord(stable_id=stable_id, payload=payload)]

    try:
        first_run_id = str(uuid.uuid4())
        assert store.write(source, "web_scrape", record, first_run_id) == 1
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, payload, fetched_at, last_checked_at "
                "FROM bronze.web_scrape_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            first_hash, first_payload, first_fetched_at, first_checked_at = (
                cur.fetchone()
            )

        assert first_payload == payload
        assert store.write(source, "web_scrape", record, str(uuid.uuid4())) == 0
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, fetched_at, last_checked_at "
                "FROM bronze.web_scrape_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            second_hash, second_fetched_at, second_checked_at = cur.fetchone()

        assert second_hash == first_hash
        assert second_fetched_at == first_fetched_at
        assert second_checked_at > first_checked_at

        changed_payload = {"html": "<main>Brightroom updated</main>"}
        third_run_id = str(uuid.uuid4())
        assert (
            store.write(
                source,
                "web_scrape",
                [RawRecord(stable_id=stable_id, payload=changed_payload)],
                third_run_id,
            )
            == 1
        )
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, payload, run_id, fetched_at "
                "FROM bronze.web_scrape_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            third_hash, third_payload, stored_run_id, third_fetched_at = cur.fetchone()

        assert third_hash != second_hash
        assert third_payload == changed_payload
        assert str(stored_run_id) == third_run_id
        assert third_fetched_at > second_fetched_at
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )


def test_mid_batch_failure_rolls_back_all_web_scrape_rows():
    store = PostgresWebScrapeIngestStore(
        PostgresWebScrapeIngestRepository(DATABASE_URL)
    )
    source = "kan83-integration-test"
    stable_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    records = [
        RawRecord(stable_id=stable_ids[0], payload={"html": "valid"}),
        RawRecord(stable_id=stable_ids[1], payload={"html": {"not", "json"}}),
    ]

    try:
        with pytest.raises(TypeError):
            store.write(source, "web_scrape", records, str(uuid.uuid4()))

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM bronze.web_scrape_ingest "
                "WHERE source = %s AND stable_id = ANY(%s)",
                (source, stable_ids),
            )
            (row_count,) = cur.fetchone()
        assert row_count == 0
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = %s AND stable_id = ANY(%s)",
                (source, stable_ids),
            )
