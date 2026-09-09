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

    A context manager: one connection and one cursor span the whole `with`
    block, so the queuer's entire call shares a single connection and a
    single transaction (see huginn.silver.ports' connection-scope note).
    `read_unmatched` therefore assumes it is called between `__enter__`
    and `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresUnmatchedSignalReader:
        """Open the connection and cursor this block's statements share."""
        self._conn = psycopg.connect(self._database_url)
        self._cur = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Commit on a clean exit, roll back if the block raised, and close
        both the cursor and the connection either way.

        Returns None so a failure inside the block still propagates: a
        repository must not swallow its caller's exception.
        """
        try:
            if self._cur is not None:
                self._cur.close()
            if self._conn is not None:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            if self._conn is not None:
                self._conn.close()
            self._cur = None
            self._conn = None
        return None

    def read_unmatched(self) -> list[tuple[str, str]]:
        self._cur.execute(_UNMATCHED_SELECT_SQL, (MatchConfidence.NO_EXISTING_MATCH,))
        return list(self._cur.fetchall())


class PostgresManualReviewQueueRepository:
    """`ManualReviewQueueWriterPort` implementation against
    silver.manual_review_queue. Knows only how to insert-if-new.

    A context manager: one connection and one cursor span the whole `with`
    block, so the queuer's entire batch shares a single connection and a
    single transaction (see huginn.silver.ports' connection-scope note).
    `insert_if_new` therefore assumes it is called between `__enter__` and
    `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresManualReviewQueueRepository:
        """Open the connection and cursor this block's statements share."""
        self._conn = psycopg.connect(self._database_url)
        self._cur = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Commit on a clean exit, roll back if the block raised, and close
        both the cursor and the connection either way.

        Returns None so a failure inside the block still propagates: a
        repository must not swallow its caller's exception.
        """
        try:
            if self._cur is not None:
                self._cur.close()
            if self._conn is not None:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            if self._conn is not None:
                self._conn.close()
            self._cur = None
            self._conn = None
        return None

    def insert_if_new(
        self, resolved_signal_id: str, candidate_company_key: str, match_score: int
    ) -> bool:
        self._cur.execute(
            _INSERT_SQL, (resolved_signal_id, candidate_company_key, match_score)
        )
        return self._cur.fetchone() is not None
