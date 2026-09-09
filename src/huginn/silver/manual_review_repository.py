"""Postgres-backed `UnmatchedSignalReaderPort` and
`ManualReviewQueueWriterPort`. See huginn.silver.ports,
huginn.silver.manual_review (the orchestrator these persist for), and
docs/entities.md's ManualReviewCandidate. Jira KAN-36.
"""

from __future__ import annotations

import psycopg

from huginn.silver.resolution import MatchConfidence

_UNMATCHED_SELECT_SQL = "SELECT id, resolved_company_key FROM silver.resolved_signals WHERE match_confidence = %s"

_INSERT_SQL = """
    INSERT INTO silver.manual_review_queue
        (resolved_signal_id, candidate_company_key, match_score, status)
    VALUES (%s, %s, %s, 'pending')
    ON CONFLICT (resolved_signal_id) DO NOTHING
    RETURNING id
"""


class PostgresUnmatchedSignalReader:
    """`UnmatchedSignalReaderPort` implementation against
    silver.resolved_signals. Knows only how to read.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def read_unmatched(self) -> list[tuple[str, str]]:
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(_UNMATCHED_SELECT_SQL, (MatchConfidence.NO_EXISTING_MATCH,))
            return list(cur.fetchall())


class PostgresManualReviewQueueRepository:
    """`ManualReviewQueueWriterPort` implementation against
    silver.manual_review_queue. Knows only how to insert-if-new.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def insert_if_new(
        self, resolved_signal_id: str, candidate_company_key: str, match_score: int
    ) -> bool:
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(
                _INSERT_SQL, (resolved_signal_id, candidate_company_key, match_score)
            )
            return cur.fetchone() is not None
