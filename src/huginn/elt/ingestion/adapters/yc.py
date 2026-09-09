"""YC directory adapter. See architecture document section 5.

No official API. Queries the public, search-only Algolia key exposed in
the directory's frontend JS directly, rather than parsing rendered pages.
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
import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import ApiSourcePort

logger = logging.getLogger(__name__)

ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_INDEX = "YCCompany_production"
ALGOLIA_QUERY_URL = (
    f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
)
ALGOLIA_API_KEY_ENV_VAR = "HUGINN_YC_ALGOLIA_API_KEY"
ALGOLIA_MAX_HITS_PER_QUERY = 1000
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_CONCURRENT_FETCHES = 8


def _algolia_api_key() -> str:
    """Read YC directory's public, search-only Algolia key from
    `HUGINN_YC_ALGOLIA_API_KEY`.

    The key is not a secret (shipped to every browser that loads the
    directory page), but its literal value is not recorded in any tracked
    doc and can rotate, so it is supplied as config rather than hardcoded.
    See architecture-notes/yc-fetch-plan.md section 2 and
    `src/huginn/config.py` for the equivalent env-var pattern.
    """
    api_key = os.environ.get(ALGOLIA_API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{ALGOLIA_API_KEY_ENV_VAR} is not set. Copy .env.example to .env "
            "and fill in YC's current Algolia secured-key blob."
        )
    return api_key


def _algolia_query(body: dict) -> dict:
    """POST one query to YC's Algolia index and return the parsed response.

    Never pass `tagFilters` in `body`: the `ycdc_public` restriction is
    already signed into the secured key. See architecture-notes/yc-fetch-plan.md
    section 2.
    """
    headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": _algolia_api_key(),
    }
    response = requests.post(
        ALGOLIA_QUERY_URL, json=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()


def _discover_batches() -> list[str]:
    """Discover the current set of `batch` facet values.

    Standard Algolia facet-count query (`hitsPerPage: 0` returns facet
    counts with no hit rows). Plain pagination and `browse` cannot reach
    the full ~6200-record directory (confirmed live, 1000-hit ceiling), so
    `fetch()` must split per-batch instead of paginating. See
    architecture-notes/yc-fetch-plan.md section 2, "Confirmed by a live
    test call" bullets 2-3.
    """
    response = _algolia_query(
        {
            "query": "",
            "facets": ["batch"],
            "hitsPerPage": 0,
            # Algolia's default cap on distinct facet values returned is 100;
            # 1000 is Algolia's own documented maximum for this parameter.
            # YC currently has ~45-50 batch values, but that grows over time,
            # so remove the ceiling risk entirely rather than just raising it.
            "maxValuesPerFacet": 1000,
        }
    )
    return list(response["facets"]["batch"].keys())


def _fetch_batch(batch: str) -> list[dict]:
    """Fetch every hit for one `batch` facet value, unmodified.

    Each batch is comfortably under the confirmed 1000-hit per-query
    ceiling (6204 total hits spread across all batches), so a single query
    per batch is sufficient; no further pagination within a batch. See
    architecture-notes/yc-fetch-plan.md section 2.

    Uses `facetFilters` (Algolia's structured `attribute:value` list form)
    rather than the `filters` string DSL: `facetFilters` needs no quoting
    or escaping of `batch`'s value, so a batch label containing a quote
    character cannot produce a malformed expression the way
    `filters: f"batch:'{batch}'"` could.
    """
    response = _algolia_query(
        {
            "query": "",
            "facetFilters": [[f"batch:{batch}"]],
            "hitsPerPage": ALGOLIA_MAX_HITS_PER_QUERY,
            "page": 0,
        }
    )
    return response["hits"]


def _total_hit_count() -> int:
    """Query the directory's true total hit count with a lightweight,
    zero-hit query, for `fetch()` to reconcile the fetched record count
    against.

    `_discover_batches` (facet enumeration, capped at `maxValuesPerFacet`
    values, and blind to a record with a missing/null `batch`) and
    `_fetch_batch` (each query capped at `ALGOLIA_MAX_HITS_PER_QUERY` hits)
    each have their own silent-truncation failure mode; this gives `fetch()`
    an independent total to compare against so under-fetching is at least
    detectable. See architecture-notes/yc-fetch-plan.md section 2.
    """
    response = _algolia_query({"query": "", "hitsPerPage": 0})
    return response["nbHits"]


class YcDirectoryAdapter(ApiSourcePort):
    source = "yc"
    mechanism = "api"

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
        batches = _discover_batches()
        logger.info("yc fetch: discovered %d batch values", len(batches))

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES) as executor:
            batch_hits = list(executor.map(_fetch_batch, batches))

        records = [
            RawRecord(stable_id=str(hit["id"]), payload=hit)
            for hits in batch_hits
            for hit in hits
        ]

        total_hits = _total_hit_count()
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
