"""YC directory adapter. See architecture document section 5.

No official API. Queries the public, search-only Algolia key exposed in
the directory's frontend JS directly, rather than parsing rendered pages.
The Algolia client itself lives in `huginn.elt.ingestion.connectors.algolia`
and is injected; this module holds only YC's own ingestion policy.
Mechanism: "api" (a direct structured query, not HTML scraping).
Fetch-plan decisions: architecture-notes/yc-fetch-plan.md (KAN-39).

KAN-7 (YC's Terms of Service vs. robots.txt legal exposure) is
accepted-but-unresolved, not a build blocker: this adapter's real
implementation was built per an explicit decision to proceed while that
question stays open. See Jira KAN-7 and docs/sources/yc-directory.md,
Open questions/risks. Nothing here resolves KAN-7.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from huginn.elt.ingestion.connectors.algolia import AlgoliaConnector
from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import ApiSourcePort

logger = logging.getLogger(__name__)

# Which index to query is YC's fact rather than the connector's, so it stays
# here and is passed to `AlgoliaConnector` at construction. See
# architecture-notes/yc-fetch-plan.md section 2.
YC_ALGOLIA_APP_ID = "45BWZJ1SGC"
YC_ALGOLIA_INDEX = "YCCompany_production"
MAX_CONCURRENT_FETCHES = 8


class YcDirectoryAdapter(ApiSourcePort):
    source = "yc"
    mechanism = "api"

    def __init__(self, algolia: AlgoliaConnector) -> None:
        """Receive the Algolia client. Required rather than defaulted so the
        adapter cannot reach the network except through an injected client.
        """
        self._algolia = algolia

    def fetch(self) -> list[RawRecord]:
        """Fetch the current YC directory by querying one Algolia query per
        `batch` facet value, with bounded concurrency.

        Plain pagination and `browse` cannot reach the full directory
        (confirmed live: 1000-hit ceiling, `browse` returns 403 for this
        key); splitting by `batch` is the resolved approach. See
        architecture-notes/yc-fetch-plan.md section 2.

        The batch-split approach has its own silent-truncation risks (a
        record with no `batch` value is never enumerated; a single batch
        exceeding the per-query hit ceiling would be truncated), so this
        also reconciles the fetched record count against the directory's
        true total hit count and logs a warning (not an error — this is a
        detectable-but-not-fatal signal) on mismatch.
        """
        start = time.monotonic()
        batches = self._algolia.discover_batches()
        logger.info("yc fetch: discovered %d batch values", len(batches))

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES) as executor:
            batch_hits = list(executor.map(self._algolia.fetch_batch, batches))

        records = [
            RawRecord(stable_id=str(hit["id"]), payload=hit)
            for hits in batch_hits
            for hit in hits
        ]

        total_hits = self._algolia.total_hit_count()
        if len(records) != total_hits:
            logger.warning(
                "yc fetch: total records fetched (%d) does not match directory's "
                "total hit count (%d) — some records may be missing or duplicated",
                len(records),
                total_hits,
            )

        duration = time.monotonic() - start
        logger.info(
            "yc fetch: fetched %d records across %d batches in %.2fs",
            len(records),
            len(batches),
            duration,
        )
        return records
