"""Atomic EU-Startups enrichment persistence for KAN-83."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from huginn.elt.bronze.watermark import compute_content_hash
from huginn.elt.ingestion.models import EnrichmentBatch, RawRecord

logger = logging.getLogger(__name__)

_SOURCE = "eu_startups"
# Enrichment lastmod is a local observation time, so only fetched page content
# participates in the hash.
_STABLE_FIELDS = ("url", "html")

_LOOKUP_RECORD_SQL = """
    SELECT payload
    FROM bronze.web_scrape_ingest
    WHERE source = %s AND stable_id = %s
    FOR UPDATE
"""

_WRITE_RECORD_SQL = """
    INSERT INTO bronze.web_scrape_ingest
        (source, stable_id, payload, content_hash, run_id)
    VALUES (%s, %s, %s, %s, %s::uuid)
    ON CONFLICT (source, stable_id) DO UPDATE
    SET payload = EXCLUDED.payload,
        content_hash = EXCLUDED.content_hash,
        run_id = EXCLUDED.run_id,
        fetched_at = now(),
        last_checked_at = now()
    WHERE bronze.web_scrape_ingest.payload ->> 'lastmod' IS NULL
       OR (bronze.web_scrape_ingest.payload ->> 'lastmod')::timestamptz
          <= (EXCLUDED.payload ->> 'lastmod')::timestamptz
"""

_TOUCH_RECORD_SQL = """
    UPDATE bronze.web_scrape_ingest
    SET last_checked_at = now()
    WHERE source = %s AND stable_id = %s
"""

_MARK_SEARCHED_SQL = """
    UPDATE gold.company
    SET eu_startups_searched_at = now()
    WHERE name = ANY(%s)
      AND eu_startups_searched_at IS NULL
"""


def _validate_record(record: RawRecord) -> datetime:
    for field in _STABLE_FIELDS:
        if not isinstance(record.payload.get(field), str):
            raise ValueError(f"EU-Startups enrichment records require string {field}")
    lastmod = record.payload.get("lastmod")
    if not isinstance(lastmod, str):
        raise ValueError("EU-Startups enrichment records require string lastmod")
    timestamp = datetime.fromisoformat(lastmod)
    if timestamp.utcoffset() is None:
        raise ValueError("EU-Startups enrichment timestamps must include an offset")
    return timestamp


def build_record_upsert_query(
    record: RawRecord, content_hash: str, run_id: str
) -> tuple[str, tuple[str, str, Jsonb, str, str]]:
    """Parameterized upsert that preserves a newer stored EU observation."""
    return _WRITE_RECORD_SQL, (
        _SOURCE,
        record.stable_id,
        Jsonb(record.payload),
        content_hash,
        run_id,
    )


def build_mark_searched_query(
    names: Sequence[str],
) -> tuple[str, tuple[list[str]]]:
    """Parameterized cursor update for every Gold row with these names."""
    return _MARK_SEARCHED_SQL, (list(names),)


class PostgresEuStartupsEnrichmentRepository:
    """One-transaction boundary for enrichment Bronze rows and Gold cursors."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def persist_batch(self, batch: EnrichmentBatch, run_id: str) -> int:
        """Atomically persist raw pages and definitive candidate outcomes."""
        uuid.UUID(run_id)
        written = 0
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            for record in batch.records:
                observed_at = _validate_record(record)
                content_hash = compute_content_hash(
                    record.payload, _STABLE_FIELDS, include_field_presence=True
                )
                cursor.execute(_LOOKUP_RECORD_SQL, (_SOURCE, record.stable_id))
                row = cursor.fetchone()
                if row is not None:
                    existing_payload = row[0]
                    existing_hash = compute_content_hash(
                        existing_payload,
                        _STABLE_FIELDS,
                        include_field_presence=True,
                    )
                    previous_lastmod = existing_payload.get("lastmod")
                    previous_at = (
                        datetime.fromisoformat(previous_lastmod)
                        if isinstance(previous_lastmod, str)
                        else None
                    )
                    # Synthetic enrichment lastmod is not a source edit time.
                    # Unchanged page content keeps the stored payload (including
                    # a sitemap lastmod) and only advances last_checked_at.
                    if existing_hash == content_hash or (
                        previous_at is not None and previous_at >= observed_at
                    ):
                        cursor.execute(_TOUCH_RECORD_SQL, (_SOURCE, record.stable_id))
                        continue

                # Changed content can replace an older observation; the SQL
                # guard also protects a newer row inserted after the lookup.
                cursor.execute(*build_record_upsert_query(record, content_hash, run_id))
                if cursor.rowcount:
                    written += cursor.rowcount
                else:
                    # A concurrent discovery insert may have won after the
                    # lookup; the upsert guard keeps it and we still record
                    # that this listing was checked.
                    cursor.execute(_TOUCH_RECORD_SQL, (_SOURCE, record.stable_id))

            if batch.definitive_names:
                cursor.execute(*build_mark_searched_query(batch.definitive_names))

        logger.info(
            "EU-Startups enrichment persisted %d records and marked %d names",
            written,
            len(batch.definitive_names),
        )
        return written
