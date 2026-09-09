"""Postgres-backed `ManualReviewRepositoryPort`. See huginn.silver.ports,
huginn.silver.manual_review (the orchestrator this persists for), and
docs/entities.md's ManualReviewCandidate. Jira KAN-36.
"""

from __future__ import annotations

from huginn.silver.postgres_repository import PostgresRepositoryScope
from huginn.silver.resolution import MatchConfidence

_UNMATCHED_SELECT_SQL = "SELECT id, resolved_company_key FROM silver.resolved_signals WHERE match_confidence = %s"

_INSERT_SQL = """
    INSERT INTO silver.manual_review_queue
        (resolved_signal_id, candidate_company_key, match_score, status)
    VALUES (%s, %s, %s, 'pending')
    ON CONFLICT (resolved_signal_id) DO NOTHING
    RETURNING id
"""


class PostgresManualReviewRepository(PostgresRepositoryScope):
    """`ManualReviewRepositoryPort` implementation: reads the unmatched
    silver.resolved_signals rows and inserts-if-new into
    silver.manual_review_queue.

    Both sides live on one class so `ManualReviewQueuer.queue_unmatched()`
    needs a single connection and a single transaction for its whole call,
    rather than one per port. Every method here is only valid between
    `__enter__` and `__exit__`.
    """

    def read_unmatched(self) -> list[tuple[str, str]]:
        self._cur.execute(_UNMATCHED_SELECT_SQL, (MatchConfidence.NO_EXISTING_MATCH,))
        return list(self._cur.fetchall())

    def insert_if_new(
        self, resolved_signal_id: str, candidate_company_key: str, match_score: int
    ) -> bool:
        self._cur.execute(
            _INSERT_SQL, (resolved_signal_id, candidate_company_key, match_score)
        )
        return self._cur.fetchone() is not None
