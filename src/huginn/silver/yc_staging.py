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

from dataclasses import dataclass
from datetime import UTC, datetime

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
