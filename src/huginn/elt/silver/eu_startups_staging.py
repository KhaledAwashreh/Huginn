"""EU-Startups staging loader: Bronze rows for source="eu_startups" ->
silver.eu_startups_listings. See architecture document section 4.2,
ADR-0001, docs/entities.md's Silver section ("Additional per-source
staging tables follow this same shape"). Jira KAN-64.

Mirrors huginn.elt.silver.hn_staging/yc_staging exactly. Field mapping,
grounded in the KAN-64 plan's Task 4 field-mapping notes and
docs/sources/eu-startups.md's field table:

- This source has no dedicated "company name" field on the listing page,
  so `company_name_raw` comes from the detail page's `<title>` tag
  ("Name | EU-Startups", confirmed present on every fixture), not
  `extract_listing_fields`'s own confirmed slugs.
- `signal_type` is always "other": a directory listing is itself neither
  a hiring post nor a funding announcement (silver.sql's signal_type
  constraint has no better fit).
- `stage` is always None: this source has no funding-stage-shaped field
  (`total_funding` is free-text, not a stage enum).
- `occurred_on` comes from the sitemap `lastmod` the ingestion adapter
  carries in `RawRecord.payload` (KAN-64 plan Global Constraint 4).
"""

from __future__ import annotations

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from huginn.elt.ingestion.adapters.eu_startups import extract_listing_fields
from huginn.elt.silver.models import EuStartupsListingStaging
from huginn.elt.silver.ports import EuStartupsStagingRepositoryPort

logger = logging.getLogger(__name__)


def _extract_title(html_text: str) -> str | None:
    """The detail page's `<title>` tag text, or None if absent. Confirmed
    present on every real fixture (e.g. "Brightroom | EU-Startups").
    """
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.title.get_text(strip=True) if soup.title else None


def _slug_from_url(url: str) -> str:
    """The listing's directory slug from its detail-page URL, mirroring
    huginn.elt.ingestion.adapters.eu_startups's `_listing_slug` (used
    there as `RawRecord.stable_id`). Reused here as this staging row's
    `stable_id` since the Bronze payload itself carries only
    `{"url", "html", "lastmod"}`, no separately-captured id.
    """
    return url.rstrip("/").rsplit("/", 1)[-1]


def parse_eu_startups_listing(payload: dict) -> EuStartupsListingStaging | None:
    """Parse one eu_startups Bronze row (raw detail-page HTML plus its
    sitemap `url`/`lastmod`), or None when the page has neither a
    `website` field nor a `<title>` tag: a genuinely empty or malformed
    fetch, not a real listing, so no row is produced rather than one full
    of None/empty values that would fail `resolve_signal`'s own handling
    downstream.
    """
    fields = extract_listing_fields(payload["html"])
    title = _extract_title(payload["html"])

    if fields["website"] is None and title is None:
        return None

    company_name_raw = title.split(" | ")[0].strip() if title else ""

    return EuStartupsListingStaging(
        stable_id=_slug_from_url(payload["url"]),
        company_name_raw=company_name_raw,
        website=fields["website"],
        signal_type="other",
        stage=None,
        description=fields["business_description"] or "",
        occurred_on=datetime.fromisoformat(payload["lastmod"]),
        url=payload["url"],
    )


class EuStartupsStagingLoader:
    """Reads Bronze rows for source="eu_startups" and upserts
    silver.eu_startups_listings via its injected port. Mirrors
    HnStagingLoader/YcStagingLoader exactly; this class holds no
    persistence detail of its own. Jira KAN-64.
    """

    def __init__(self, repository: EuStartupsStagingRepositoryPort) -> None:
        self._repository = repository

    def load(self) -> int:
        """Parse and upsert every current eu_startups Bronze row,
        returning the count of rows upserted (excludes rows
        `parse_eu_startups_listing` skips as malformed).
        """
        # See huginn.elt.silver.ports's module docstring for why this whole
        # method shares one `with self._repository:` scope.
        with self._repository:
            payloads = self._repository.read("eu_startups")
            written = 0
            for payload in payloads:
                staging_row = parse_eu_startups_listing(payload)
                if staging_row is None:
                    continue
                self._repository.upsert(staging_row)
                written += 1

        logger.info(
            "silver.eu_startups_listings load: %d written (of %d bronze rows)",
            written,
            len(payloads),
        )
        return written
