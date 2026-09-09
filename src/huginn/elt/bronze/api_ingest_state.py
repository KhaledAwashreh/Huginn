"""StatePort: a thin read against bronze.api_ingest for the last stored
content_hash of a (source, stable_id) pair. See architecture document
section 4.1 point 4 (content-hash watermark) and section 5 (StatePort's
role in the ingestion ports diagram). ADR-0005: logging required from day
one.

Shares its lookup with huginn.elt.bronze.api_ingest_store (Jira KAN-32):
RawStorePort's write path and StatePort's read both need exactly the
"stored content_hash for (source, stable_id)" query against the same
table. Both now go through the same injected `ApiIngestRepositoryPort`,
so the query exists once, in the repository, rather than being issued
independently from two classes.

Nothing calls this class yet; Jira KAN-46 tracks deciding its role or
removing it.
"""

from __future__ import annotations

import logging

from huginn.elt.bronze.ports import ApiIngestRepositoryPort

logger = logging.getLogger(__name__)


class PostgresApiIngestState:
    """`StatePort` implementation against `bronze.api_ingest` only. See
    architecture document section 4.1 and section 5, and this plan's
    Global Constraint 2 (shared lookup query) and Constraint 4 (DEBUG-level
    per-call logging).
    """

    def __init__(self, repository: ApiIngestRepositoryPort) -> None:
        self._repository = repository

    def last_hash(self, source: str, stable_id: str) -> str | None:
        """See huginn.elt.bronze.ports.StatePort.last_hash."""
        result = self._repository.lookup_hash(source, stable_id)
        logger.debug(
            "bronze.api_ingest lookup source=%s stable_id=%s: %s",
            source,
            stable_id,
            "hit" if result is not None else "miss",
        )
        return result
