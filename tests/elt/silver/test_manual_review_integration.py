"""Live-Postgres integration coverage for ManualReviewQueuer.

Runs against the throwaway Postgres that tests/conftest.py provisions,
fails rather than skips when testcontainers or Docker is unavailable (tests/conftest.py explains why).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg

from huginn.elt.silver.manual_review import ManualReviewQueuer
from huginn.elt.silver.repositories.manual_review_repository import (
    PostgresManualReviewRepository,
)


def _build_queuer(database_url: str) -> ManualReviewQueuer:
    return ManualReviewQueuer(PostgresManualReviewRepository(database_url))


def _insert_resolved_signal(cur, source_stable_id: str, key_derivation: str) -> str:
    """Insert a Silver signal with the requested key-derivation status."""
    cur.execute(
        """
        INSERT INTO silver.resolved_signals
            (source_stable_id, source, resolved_company_key, company_name_raw,
             signal_type, occurred_on, url, key_derivation)
        VALUES (%s, 'hn', %s, 'ManualReviewTestCo', 'hiring', %s, 'https://example.invalid', %s)
        RETURNING id
        """,
        (
            source_stable_id,
            f"unresolved:hn:{source_stable_id}",
            datetime.now(UTC),
            key_derivation,
        ),
    )
    return cur.fetchone()[0]


def test_queue_unmatched_inserts_a_pending_row_for_unresolved(
    integration_database_url: str,
):
    """Queue an unresolved Silver signal for pending manual review."""
    source_stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        resolved_signal_id = _insert_resolved_signal(
            cur, source_stable_id, "unresolved"
        )

    try:
        written = _build_queuer(integration_database_url).queue_unmatched()

        assert written >= 1

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT candidate_company_key, match_score, status "
                "FROM silver.manual_review_queue WHERE resolved_signal_id = %s",
                (resolved_signal_id,),
            )
            candidate_company_key, match_score, status = cur.fetchone()

        assert candidate_company_key == f"unresolved:hn:{source_stable_id}"
        assert match_score == 0
        assert status == "pending"
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.manual_review_queue WHERE resolved_signal_id = %s",
                (resolved_signal_id,),
            )
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE id = %s",
                (resolved_signal_id,),
            )


def test_queue_unmatched_does_not_queue_a_domain_normalized_signal(
    integration_database_url: str,
):
    """Do not queue a signal whose company domain was normalized."""
    source_stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        resolved_signal_id = _insert_resolved_signal(
            cur, source_stable_id, "domain_normalized"
        )

    try:
        _build_queuer(integration_database_url).queue_unmatched()

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM silver.manual_review_queue WHERE resolved_signal_id = %s",
                (resolved_signal_id,),
            )
            assert cur.fetchone()[0] == 0
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE id = %s",
                (resolved_signal_id,),
            )


def test_queue_unmatched_does_not_duplicate_an_already_queued_row(
    integration_database_url: str,
):
    """Keep queue insertion idempotent for an unresolved signal."""
    source_stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        resolved_signal_id = _insert_resolved_signal(
            cur, source_stable_id, "unresolved"
        )

    try:
        queuer = _build_queuer(integration_database_url)
        first_written = queuer.queue_unmatched()
        second_written = queuer.queue_unmatched()

        assert first_written >= 1
        assert second_written == 0

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM silver.manual_review_queue WHERE resolved_signal_id = %s",
                (resolved_signal_id,),
            )
            assert cur.fetchone()[0] == 1
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.manual_review_queue WHERE resolved_signal_id = %s",
                (resolved_signal_id,),
            )
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE id = %s",
                (resolved_signal_id,),
            )
