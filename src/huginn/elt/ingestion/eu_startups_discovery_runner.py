"""Dedicated transactional runner for EU-Startups sitemap discovery."""

from __future__ import annotations

import logging
import uuid

from huginn.elt.bronze.ports import EuStartupsDiscoveryRepositoryPort
from huginn.elt.ingestion.adapters.eu_startups import EuStartupsDiscoveryAdapter

logger = logging.getLogger(__name__)


class EuStartupsDiscoveryRunner:
    """Coordinate EU discovery without changing ``IngestionService``.

    The source-specific repository owns every durable state transition, so a
    failed commit leaves its watermark and retry list unchanged.
    """

    def __init__(
        self,
        adapter: EuStartupsDiscoveryAdapter,
        repository: EuStartupsDiscoveryRepositoryPort,
    ) -> None:
        self._adapter = adapter
        self._repository = repository

    def run(self, run_id: str | None = None) -> int:
        """Fetch a batch from durable state and atomically persist it."""
        watermark = self._repository.read_watermark()
        retryable_listings = self._repository.list_retryable_listings()
        batch = self._adapter.fetch(watermark, retryable_listings)
        written = self._repository.commit_batch(batch, run_id or str(uuid.uuid4()))
        logger.info(
            "EU-Startups discovery succeeded: %d written, %d failed",
            written,
            len(batch.failed_listings),
        )
        return written
