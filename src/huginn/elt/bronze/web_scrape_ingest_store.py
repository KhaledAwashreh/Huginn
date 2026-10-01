"""Raw-store orchestration for `bronze.web_scrape_ingest`."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence

from huginn.elt.bronze.api_ingest_store import ACTION_WRITE, decide_write_action
from huginn.elt.bronze.ports import WebScrapeIngestRepositoryPort
from huginn.elt.bronze.watermark import compute_content_hash
from huginn.elt.ingestion.models import RawRecord

logger = logging.getLogger(__name__)

_ATOMIC_DISCOVERY_SOURCES = frozenset({"eu_startups"})


class PostgresWebScrapeIngestStore:
    """`RawStorePort` implementation for web-scrape Bronze rows only."""

    def __init__(
        self,
        repository: WebScrapeIngestRepositoryPort,
        stable_fields_by_source: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        if repository.bronze_table != "web_scrape_ingest":
            raise ValueError(
                "PostgresWebScrapeIngestStore requires a repository for "
                "bronze.web_scrape_ingest"
            )
        self._repository = repository
        self._stable_fields_by_source = {
            source: tuple(stable_fields)
            for source, stable_fields in (stable_fields_by_source or {}).items()
        }

    def write(
        self, source: str, mechanism: str, records: list[RawRecord], run_id: str
    ) -> int:
        if mechanism != "web_scrape":
            raise NotImplementedError(
                "PostgresWebScrapeIngestStore only writes "
                "bronze.web_scrape_ingest ('web_scrape' mechanism); "
                f"got mechanism={mechanism!r}."
            )
        if source in _ATOMIC_DISCOVERY_SOURCES:
            raise ValueError(
                f"source {source!r} requires its dedicated atomic discovery runner"
            )

        try:
            uuid.UUID(run_id)
        except ValueError as exc:
            raise ValueError(
                f"run_id must be a valid UUID string; got {run_id!r}"
            ) from exc

        written = 0
        skipped = 0
        with self._repository:
            for record in records:
                has_configured_stable_fields = source in self._stable_fields_by_source
                stable_fields = self._stable_fields_by_source.get(
                    source, tuple(record.payload.keys())
                )
                content_hash = compute_content_hash(
                    record.payload,
                    stable_fields,
                    include_field_presence=has_configured_stable_fields,
                )
                existing_hash = self._repository.lookup_hash(source, record.stable_id)

                if decide_write_action(existing_hash, content_hash) == ACTION_WRITE:
                    self._repository.write(
                        source,
                        record.stable_id,
                        record.payload,
                        content_hash,
                        run_id,
                    )
                    written += 1
                else:
                    self._repository.touch(source, record.stable_id)
                    skipped += 1

        logger.info(
            "bronze.web_scrape_ingest write source=%s run_id=%s: "
            "%d written, %d skipped",
            source,
            run_id,
            written,
            skipped,
        )
        return written
