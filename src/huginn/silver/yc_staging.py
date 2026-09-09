"""YC staging loader: bronze.api_ingest (source="yc") -> silver.yc_listings.
See architecture document section 4.2, ADR-0001, docs/entities.md's
YcListingStaging. Jira KAN-34.

signal_type follows isHiring: "hiring" when true, "program_milestone"
otherwise (the listing itself, whatever its current hiring state, is
still a trackable signal; the payload carries no funding data, so
"funding" is never produced here). Confirmed live: exactly two `stage`
values exist ("Early", "Growth"), passed through unmapped. See this
plan's Task 4 "Grounding" note.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

logger = logging.getLogger(__name__)

_YC_COMPANY_URL = "https://www.ycombinator.com/companies/{slug}"


@dataclass(frozen=True)
class YcListingStaging:
    """One row of silver.yc_listings. See docs/entities.md's YcListingStaging."""

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str


def parse_yc_listing(payload: dict) -> YcListingStaging:
    """Parse one YC Algolia hit. Never returns None: `id`, `name`, and
    `slug` are present on 100% of the live directory (confirmed, this
    plan's Task 4), unlike HN's freeform comments.
    """
    description = payload.get("long_description") or payload["one_liner"]

    return YcListingStaging(
        stable_id=str(payload["id"]),
        company_name_raw=payload["name"],
        website=payload.get("website"),
        signal_type="hiring" if payload.get("isHiring") else "program_milestone",
        stage=payload.get("stage"),
        description=description,
        occurred_on=datetime.fromtimestamp(payload["launched_at"], tz=UTC),
        url=_YC_COMPANY_URL.format(slug=payload["slug"]),
    )


_BRONZE_YC_SELECT_SQL = "SELECT payload FROM bronze.api_ingest WHERE source = 'yc'"

_UPSERT_SQL = """
    INSERT INTO silver.yc_listings
        (stable_id, company_name_raw, website, signal_type, stage,
         description, occurred_on, url)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (stable_id) DO UPDATE
    SET company_name_raw = EXCLUDED.company_name_raw,
        website = EXCLUDED.website,
        signal_type = EXCLUDED.signal_type,
        stage = EXCLUDED.stage,
        description = EXCLUDED.description,
        occurred_on = EXCLUDED.occurred_on,
        url = EXCLUDED.url,
        updated_at = now()
"""


def build_upsert_query(row: YcListingStaging) -> tuple[str, tuple]:
    """Parameterized upsert for one staging row, keyed on stable_id
    (this plan's Task 1 unique constraint)."""
    return _UPSERT_SQL, (
        row.stable_id,
        row.company_name_raw,
        row.website,
        row.signal_type,
        row.stage,
        row.description,
        row.occurred_on,
        row.url,
    )


class PostgresYcStagingLoader:
    """Reads bronze.api_ingest (source="yc") and upserts silver.yc_listings.
    See docs/entities.md's YcListingStaging and ADR-0001. Jira KAN-34.

    Reads every bronze row for the source each run rather than tracking
    its own watermark: silver.yc_listings' UNIQUE(stable_id) upsert
    already makes re-processing idempotent, mirroring Bronze's own
    hash-based idempotency (architecture document section 4.1). The
    upsert still writes every row on every run; it is the resulting
    database state, not the work done, that is unchanged.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def load(self) -> int:
        """Parse and upsert every current YC bronze row, returning the
        count of rows upserted (always equals the input count; the write
        executes on every row even when nothing changed).
        """
        written = 0
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(_BRONZE_YC_SELECT_SQL)
            payloads = [row[0] for row in cur.fetchall()]

            for payload in payloads:
                staging_row = parse_yc_listing(payload)
                cur.execute(*build_upsert_query(staging_row))
                written += 1

        logger.info(
            "silver.yc_listings load: %d written (of %d bronze rows)",
            written,
            len(payloads),
        )
        return written
