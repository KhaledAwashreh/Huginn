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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from huginn.silver.ports import YcStagingRepositoryPort

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


class YcStagingLoader:
    """Reads bronze.api_ingest (source="yc") and upserts silver.yc_listings
    via its injected port. See docs/entities.md's YcListingStaging and
    ADR-0001. Jira KAN-34. See huginn.silver.ports for the port
    contract; this class holds no persistence detail of its own.

    Reads every bronze row for the source each run rather than tracking
    its own watermark: silver.yc_listings' UNIQUE(stable_id) upsert
    already makes re-processing idempotent, mirroring Bronze's own
    hash-based idempotency (architecture document section 4.1). The
    upsert still writes every row on every run; it is the resulting
    database state, not the work done, that is unchanged.
    """

    def __init__(self, repository: YcStagingRepositoryPort) -> None:
        self._repository = repository

    def load(self) -> int:
        """Parse and upsert every current YC bronze row, returning the
        count of rows upserted (always equals the input count; the write
        executes on every row even when nothing changed).
        """
        # One `with` around the whole method, not one per record: every
        # statement in this call shares a single connection and commits as
        # one transaction, so a large run costs one connect rather than one
        # per record, and a mid-loop failure leaves no partial batch
        # behind. `with` on an injected port is plain Python; this class
        # still imports no `psycopg`.
        with self._repository:
            payloads = self._repository.read("yc")
            written = 0
            for payload in payloads:
                staging_row = parse_yc_listing(payload)
                self._repository.upsert(staging_row)
                written += 1

        logger.info(
            "silver.yc_listings load: %d written (of %d bronze rows)",
            written,
            len(payloads),
        )
        return written
