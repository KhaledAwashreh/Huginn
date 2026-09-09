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

from huginn.elt.silver.ports import ManualReviewRepositoryPort

logger = logging.getLogger(__name__)

NO_SCORE_COMPUTED = 0


class ManualReviewQueuer:
    """Queues every unmatched silver.resolved_signals row exactly once,
    via its injected port. See docs/entities.md's ManualReviewCandidate.
    Jira KAN-36. See huginn.elt.silver.ports for the port contract; this
    class holds no persistence detail of its own.
    """

    def __init__(self, repository: ManualReviewRepositoryPort) -> None:
        self._repository = repository

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
        # See huginn.elt.silver.ports's module docstring for why this whole
        # method shares one `with self._repository:` scope.
        with self._repository:
            written = 0
            for (
                resolved_signal_id,
                candidate_company_key,
            ) in self._repository.read_unmatched():
                if self._repository.insert_if_new(
                    resolved_signal_id, candidate_company_key, NO_SCORE_COMPUTED
                ):
                    written += 1

        logger.info("silver.manual_review_queue queue_unmatched: %d written", written)
        return written
