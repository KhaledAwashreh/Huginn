"""Transactional EU-Startups discovery persistence for KAN-83."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import psycopg
from psycopg.types.json import Jsonb

from huginn.elt.bronze.watermark import compute_content_hash
from huginn.elt.ingestion.models import DiscoveryBatch

logger = logging.getLogger(__name__)

RETRYABLE = "retryable"
TERMINAL = "terminal"
RetryStatus = Literal["retryable", "terminal"]

_SOURCE = "eu_startups"
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
"""

_TOUCH_RECORD_SQL = """
    UPDATE bronze.web_scrape_ingest
    SET last_checked_at = now()
    WHERE source = %s AND stable_id = %s
"""

_CLEAR_RETRY_SQL = """
    DELETE FROM bronze.eu_startups_listing_retry
    WHERE url = %s
"""

_WRITE_RETRY_SQL = """
    INSERT INTO bronze.eu_startups_listing_retry
        (url, lastmod, attempt_count, terminal_attempt_count,
         last_status_code, status)
    VALUES (%s, %s::timestamptz, 1, %s, %s, 'retryable')
    ON CONFLICT (url) DO UPDATE
    SET lastmod = EXCLUDED.lastmod,
        attempt_count = bronze.eu_startups_listing_retry.attempt_count + 1,
        terminal_attempt_count =
            bronze.eu_startups_listing_retry.terminal_attempt_count
            + EXCLUDED.terminal_attempt_count,
        last_status_code = EXCLUDED.last_status_code,
        status = CASE
            WHEN bronze.eu_startups_listing_retry.status = 'terminal'
              OR bronze.eu_startups_listing_retry.terminal_attempt_count
                 + EXCLUDED.terminal_attempt_count >= %s
            THEN 'terminal'
            ELSE 'retryable'
        END,
        updated_at = now()
    RETURNING attempt_count, terminal_attempt_count, status
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


@dataclass(frozen=True)
class ListingRetryState:
    """Durable counters and policy state for one failed listing."""

    attempt_count: int
    terminal_attempt_count: int
    status: RetryStatus


def advance_retry_state(
    previous: ListingRetryState | None, status_code: int | None
) -> ListingRetryState:
    """Apply the KAN-83 three-confirmed-404/410 terminal policy."""
    attempt_count = 1 if previous is None else previous.attempt_count + 1
    terminal_attempt_count = 0 if previous is None else previous.terminal_attempt_count
    if status_code in _TERMINAL_STATUS_CODES:
        terminal_attempt_count += 1

    already_terminal = previous is not None and previous.status == TERMINAL
    status: RetryStatus = (
        TERMINAL
        if already_terminal or terminal_attempt_count >= _TERMINAL_ATTEMPTS
        else RETRYABLE
    )
    return ListingRetryState(attempt_count, terminal_attempt_count, status)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("EU-Startups discovery timestamps must include an offset")
    return parsed


def committed_watermark(
    batch: DiscoveryBatch, failure_statuses: tuple[RetryStatus, ...]
) -> datetime | None:
    """Choose the watermark after applying durable failure policy."""
    if len(failure_statuses) != len(batch.failed_listings):
        raise ValueError("one retry status is required for each failed listing")

    retryable_lastmods = [
        _parse_timestamp(failure.lastmod)
        for failure, status in zip(batch.failed_listings, failure_statuses, strict=True)
        if status == RETRYABLE
    ]
    if retryable_lastmods:
        return min(retryable_lastmods) - timedelta(seconds=1)

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

    def commit_batch(self, batch: DiscoveryBatch, run_id: str) -> int:
        """Commit Bronze rows, retry state, and watermark in one transaction."""
        uuid.UUID(run_id)
        written = 0
        connection = psycopg.connect(self._database_url)
        cursor = None

        try:
            cursor = connection.cursor()
            for record in batch.records:
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
                    written += 1
                else:
                    cursor.execute(_TOUCH_RECORD_SQL, (_SOURCE, record.stable_id))

                listing_url = record.payload.get("url")
                if not isinstance(listing_url, str):
                    raise ValueError(
                        "EU-Startups discovery records require a string URL"
                    )
                cursor.execute(_CLEAR_RETRY_SQL, (listing_url,))

            failure_statuses: list[RetryStatus] = []
            for failure in batch.failed_listings:
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
                _attempts, _terminal_attempts, status = cursor.fetchone()
                failure_statuses.append(status)

            watermark = committed_watermark(batch, tuple(failure_statuses))
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
