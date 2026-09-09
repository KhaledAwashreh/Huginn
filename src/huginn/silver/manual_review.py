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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from huginn.silver.ports import (
        ManualReviewQueueWriterPort,
        UnmatchedSignalReaderPort,
    )

logger = logging.getLogger(__name__)

NO_SCORE_COMPUTED = 0


class ManualReviewQueuer:
    """Queues every unmatched silver.resolved_signals row exactly once,
    via its injected ports. See docs/entities.md's ManualReviewCandidate.
    Jira KAN-36. See huginn.silver.ports for the port contracts; this
    class holds no persistence detail of its own.
    """

    def __init__(
        self,
        unmatched_reader: UnmatchedSignalReaderPort,
        queue_writer: ManualReviewQueueWriterPort,
    ) -> None:
        self._unmatched_reader = unmatched_reader
        self._queue_writer = queue_writer

    def queue_unmatched(self) -> int:
        """Insert a pending queue row for every 'no_existing_match'
        resolved_signals row not already queued, returning the count of
        rows newly inserted (excludes rows already queued, so a rerun
        with no new unmatched signals returns 0). Unlike the staging
        loaders' and the resolver's return values, this is not the
        input count.

        A row already queued — pending, confirmed, or rejected — is left
        untouched: re-running this must never reset a reviewer's prior
        decision.
        """
        # One `with` around the whole method, not one per record: the read
        # and every insert in this call share a single connection per port
        # and commit as one transaction, so a large run costs one connect
        # rather than one per record, and a mid-loop failure leaves no
        # partial batch behind. `with` on an injected port is plain
        # Python; this class still imports no `psycopg`.
        with self._unmatched_reader, self._queue_writer:
            written = 0
            for (
                resolved_signal_id,
                candidate_company_key,
            ) in self._unmatched_reader.read_unmatched():
                if self._queue_writer.insert_if_new(
                    resolved_signal_id, candidate_company_key, NO_SCORE_COMPUTED
                ):
                    written += 1

        logger.info("silver.manual_review_queue queue_unmatched: %d written", written)
        return written
