"""Manual review queue writer: silver.resolved_signals rows with
match_confidence='no_existing_match' -> silver.manual_review_queue. See
architecture document section 6, docs/entities.md's
ManualReviewCandidate. Jira KAN-36.

match_score=0 documents "no similarity score was computed" (no domain,
no fuzzy-match implementation, Jira KAN-4) — distinct from a real
0.85-0.92 fuzzy-match band score (architecture document section 6). See
this plan's Task 7.
"""

from __future__ import annotations

import logging

import psycopg

from huginn.silver.resolution import MatchConfidence

logger = logging.getLogger(__name__)

NO_SCORE_COMPUTED = 0

_UNMATCHED_SELECT_SQL = "SELECT id, resolved_company_key FROM silver.resolved_signals WHERE match_confidence = %s"

_INSERT_SQL = """
    INSERT INTO silver.manual_review_queue
        (resolved_signal_id, candidate_company_key, match_score, status)
    VALUES (%s, %s, %s, 'pending')
    ON CONFLICT (resolved_signal_id) DO NOTHING
    RETURNING id
"""


class PostgresManualReviewQueueWriter:
    """Queues every unmatched silver.resolved_signals row exactly once.
    See docs/entities.md's ManualReviewCandidate. Jira KAN-36.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def queue_unmatched(self) -> int:
        """Insert a pending queue row for every 'no_existing_match'
        resolved_signals row not already queued (this plan's Task 1
        UNIQUE(resolved_signal_id) constraint makes the ON CONFLICT DO
        NOTHING a no-op for one already present), returning the count
        actually inserted. A row already queued — pending, confirmed, or
        rejected — is left untouched: re-running this must never reset a
        reviewer's prior decision.
        """
        written = 0
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(_UNMATCHED_SELECT_SQL, (MatchConfidence.NO_EXISTING_MATCH,))
            rows = cur.fetchall()
            for resolved_signal_id, candidate_company_key in rows:
                cur.execute(
                    _INSERT_SQL,
                    (resolved_signal_id, candidate_company_key, NO_SCORE_COMPUTED),
                )
                if cur.fetchone() is not None:
                    written += 1

        logger.info("silver.manual_review_queue queue_unmatched: %d written", written)
        return written
