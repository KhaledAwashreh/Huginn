from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EuStartupsListingStaging:
    """One row of silver.eu_startups_listings. Same per-source staging
    shape as HnPostingStaging/YcListingStaging (docs/entities.md's Silver
    section: "Additional per-source staging tables follow this same
    shape"). Jira KAN-64. `stage` and `occurred_on` don't map naturally
    from a directory listing; see huginn.elt.silver.eu_startups_staging's
    `parse_eu_startups_listing` for what is stored there instead.
    """

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str
    founded: str | None = None
    total_funding: str | None = None
    company_status: str | None = None
