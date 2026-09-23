"""Transactional EU-Startups discovery persistence for KAN-83."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from huginn.elt.bronze.watermark import compute_content_hash
from huginn.elt.ingestion.models import DiscoveryBatch, FailedListingOutcome

logger = logging.getLogger(__name__)

RETRYABLE = "retryable"
TERMINAL = "terminal"

_SOURCE = "eu_startups"
_COMMIT_LOCK_KEY = (0x48554749, 0x45555354)  # Huginn / EU-Startups: "HUGI", "EUST".
_TERMINAL_STATUS_CODES = frozenset({404, 410})
_TERMINAL_ATTEMPTS = 3

_READ_WATERMARK_SQL = """
    SELECT watermark
    FROM bronze.eu_startups_discovery_state
    WHERE singleton = TRUE
"""

_LOOKUP_HASH_SQL = """
    SELECT content_hash
    FROM bronze.web_scrape_ingest
    WHERE source = %s AND stable_id = %s
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
    WHERE (bronze.web_scrape_ingest.payload ->> 'lastmod')::timestamptz
          <= (EXCLUDED.payload ->> 'lastmod')::timestamptz
"""

_TOUCH_RECORD_SQL = """
    UPDATE bronze.web_scrape_ingest
    SET last_checked_at = now()
    WHERE source = %s AND stable_id = %s
"""

_READ_SUCCESSFUL_LISTING_LASTMOD_SQL = """
    SELECT MAX((payload ->> 'lastmod')::timestamptz)
    FROM bronze.web_scrape_ingest
    WHERE source = %s AND payload ->> 'url' = %s
"""

_CLEAR_RETRY_SQL = """
    DELETE FROM bronze.eu_startups_listing_retry
    WHERE url = %s AND lastmod <= %s::timestamptz
"""

_LIST_RETRYABLE_SQL = """
    SELECT url, lastmod, last_status_code
    FROM bronze.eu_startups_listing_retry
    WHERE status = 'retryable'
    ORDER BY lastmod, url
"""

_WRITE_RETRY_SQL = """
    INSERT INTO bronze.eu_startups_listing_retry
        (url, lastmod, attempt_count, terminal_attempt_count,
         last_status_code, status)
    VALUES (%s, %s::timestamptz, 1, %s, %s, 'retryable')
    ON CONFLICT (url) DO UPDATE
    SET lastmod = EXCLUDED.lastmod,
        attempt_count = CASE
            WHEN EXCLUDED.lastmod > bronze.eu_startups_listing_retry.lastmod THEN 1
            ELSE bronze.eu_startups_listing_retry.attempt_count + 1
        END,
        terminal_attempt_count = CASE
            WHEN EXCLUDED.lastmod > bronze.eu_startups_listing_retry.lastmod
            THEN EXCLUDED.terminal_attempt_count
            ELSE bronze.eu_startups_listing_retry.terminal_attempt_count
                 + EXCLUDED.terminal_attempt_count
        END,
        last_status_code = EXCLUDED.last_status_code,
        status = CASE
            WHEN EXCLUDED.lastmod > bronze.eu_startups_listing_retry.lastmod
            THEN 'retryable'
            WHEN bronze.eu_startups_listing_retry.status = 'terminal'
              OR (EXCLUDED.terminal_attempt_count = 1
                  AND bronze.eu_startups_listing_retry.attempt_count + 1 >= %s)
            THEN 'terminal'
            ELSE 'retryable'
        END,
        updated_at = now()
    WHERE EXCLUDED.lastmod >= bronze.eu_startups_listing_retry.lastmod
"""

_WRITE_WATERMARK_SQL = """
    INSERT INTO bronze.eu_startups_discovery_state (singleton, watermark)
    VALUES (TRUE, %s)
    ON CONFLICT (singleton) DO UPDATE
    SET watermark = GREATEST(
            bronze.eu_startups_discovery_state.watermark,
            EXCLUDED.watermark
        ),
        updated_at = now()
"""


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("EU-Startups discovery timestamps must include an offset")
    return parsed


def committed_watermark(
    batch: DiscoveryBatch, retryable_lastmods: tuple[str, ...]
) -> datetime | None:
    """Choose the watermark after applying durable failure policy."""
    if retryable_lastmods:
        return min(map(_parse_timestamp, retryable_lastmods)) - timedelta(seconds=1)

    if batch.failed_listings:
        processed_lastmods = [
            _parse_timestamp(failure.lastmod) for failure in batch.failed_listings
        ]
        processed_lastmods.extend(
            _parse_timestamp(record.payload["lastmod"]) for record in batch.records
        )
        if batch.proposed_watermark is not None:
            processed_lastmods.append(_parse_timestamp(batch.proposed_watermark))
        return max(processed_lastmods)

    if batch.proposed_watermark is None:
        return None
    return _parse_timestamp(batch.proposed_watermark)


def _read_retryable_listings(cursor) -> tuple[FailedListingOutcome, ...]:
    cursor.execute(_LIST_RETRYABLE_SQL)
    return tuple(
        FailedListingOutcome(
            url=url,
            lastmod=lastmod.isoformat(),
            status_code=last_status_code,
        )
        for url, lastmod, last_status_code in cursor.fetchall()
    )


class PostgresEuStartupsDiscoveryRepository:
    """PostgreSQL implementation of the KAN-83 persistence boundary."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def read_watermark(self) -> str | None:
        """Read the durable EU sitemap checkpoint."""
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(_READ_WATERMARK_SQL)
            row = cursor.fetchone()

        value = row[0].isoformat() if row is not None else None
        logger.debug("EU-Startups discovery watermark read: %s", value or "unset")
        return value

    def list_retryable_listings(self) -> tuple[FailedListingOutcome, ...]:
        """List durable retryable listings for Task 3's replay path."""
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            listings = _read_retryable_listings(cursor)

        logger.debug("EU-Startups retryable listings read: %d", len(listings))
        return listings

    def commit_batch(self, batch: DiscoveryBatch, run_id: str) -> int:
        """Commit Bronze rows, retry state, and watermark in one transaction."""
        uuid.UUID(run_id)
        written = 0
        connection = psycopg.connect(self._database_url)
        cursor = None

        try:
            cursor = connection.cursor()
            # Keep retry visibility and checkpoint writes serialized across batches.
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", _COMMIT_LOCK_KEY)
            for record in batch.records:
                record_lastmod = record.payload.get("lastmod")
                if not isinstance(record_lastmod, str):
                    raise ValueError(
                        "EU-Startups discovery records require a string lastmod"
                    )
                _parse_timestamp(record_lastmod)
                content_hash = compute_content_hash(
                    record.payload,
                    tuple(record.payload),
                    include_field_presence=True,
                )
                cursor.execute(_LOOKUP_HASH_SQL, (_SOURCE, record.stable_id))
                existing = cursor.fetchone()
                if existing is None or existing[0] != content_hash:
                    cursor.execute(
                        _WRITE_RECORD_SQL,
                        (
                            _SOURCE,
                            record.stable_id,
                            Jsonb(record.payload),
                            content_hash,
                            run_id,
                        ),
                    )
                    written += cursor.rowcount
                else:
                    cursor.execute(_TOUCH_RECORD_SQL, (_SOURCE, record.stable_id))

                listing_url = record.payload.get("url")
                if not isinstance(listing_url, str):
                    raise ValueError(
                        "EU-Startups discovery records require a string URL"
                    )
                cursor.execute(_CLEAR_RETRY_SQL, (listing_url, record_lastmod))

            applied_failures = []
            for failure in batch.failed_listings:
                failure_lastmod = _parse_timestamp(failure.lastmod)
                cursor.execute(
                    _READ_SUCCESSFUL_LISTING_LASTMOD_SQL, (_SOURCE, failure.url)
                )
                successful_lastmod = cursor.fetchone()[0]
                if (
                    successful_lastmod is not None
                    and failure_lastmod < successful_lastmod
                ):
                    logger.info(
                        "Ignoring stale EU-Startups failure for %s at %s; "
                        "Bronze already has %s",
                        failure.url,
                        failure.lastmod,
                        successful_lastmod.isoformat(),
                    )
                    continue

                terminal_increment = int(failure.status_code in _TERMINAL_STATUS_CODES)
                cursor.execute(
                    _WRITE_RETRY_SQL,
                    (
                        failure.url,
                        failure.lastmod,
                        terminal_increment,
                        failure.status_code,
                        _TERMINAL_ATTEMPTS,
                    ),
                )
                applied_failures.append(failure)

            retryable_listings = _read_retryable_listings(cursor)
            effective_batch = DiscoveryBatch(
                records=batch.records,
                proposed_watermark=batch.proposed_watermark,
                failed_listings=tuple(applied_failures),
            )
            watermark = None
            if batch.records or applied_failures or not batch.failed_listings:
                watermark = committed_watermark(
                    effective_batch,
                    tuple(listing.lastmod for listing in retryable_listings),
                )
            if watermark is not None:
                cursor.execute(_WRITE_WATERMARK_SQL, (watermark,))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                connection.close()

        logger.info(
            "EU-Startups discovery committed: %d written, %d failures, watermark=%s",
            written,
            len(batch.failed_listings),
            watermark.isoformat() if watermark is not None else "unchanged",
        )
        return written
