"""Algolia client for the YC company directory index. See architecture
document section 5 and architecture-notes/yc-fetch-plan.md (KAN-39).

Scope caveat, since the class name reads more generically than the class is:
`discover_batches` and `fetch_batch` are welded to YC's `batch` facet, so this
is an Algolia client shaped for one index family, not a reusable generic
Algolia client. The wire half (headers, POST, `raise_for_status`, JSON parse,
URL construction) is generic. Split the batch-specific methods out if a second
consumer with different facet semantics ever needs them.
"""

from __future__ import annotations

import requests

ALGOLIA_MAX_HITS_PER_QUERY = 1000
DEFAULT_TIMEOUT_SECONDS = 10.0


class AlgoliaConnector:
    """Read-only client for one Algolia index, constructed with the app ID,
    index name, and search-only API key its caller needs.

    Stateless by design. The YC adapter calls `fetch_batch` concurrently from
    a `ThreadPoolExecutor` with several workers on a single shared instance
    (ADR-0003), so this deliberately uses module-level `requests.post` rather
    than a `requests.Session`, which is documented as not thread-safe. A
    connection-pooling `Session` here would be a bug that only surfaces under
    concurrency; thread-local sessions would be the fix if pooling is ever
    wanted.
    """

    def __init__(
        self,
        app_id: str,
        index: str,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Capture the index identity and key. `app_id` and `index` are
        constructor arguments rather than constants because Algolia has many
        indexes, making them genuinely per-consumer configuration.

        `api_key` is the directory's public, search-only key. It is not a
        secret (shipped to every browser that loads the directory page), but
        its literal value is not recorded in any tracked doc and can rotate,
        so it is supplied as config rather than hardcoded. See
        architecture-notes/yc-fetch-plan.md section 2.

        Never pass `tagFilters` in a query body: the `ycdc_public` restriction
        is already signed into the secured key, so the restriction travels with
        the key rather than with any particular request.
        """
        self._app_id = app_id
        self._index = index
        self._api_key = api_key
        self._timeout = timeout
        self._query_url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index}/query"

    def query(self, body: dict) -> dict:
        """POST one query to the index and return the parsed response.

        The wire primitive the three methods below build on. A non-2xx
        response raises through `raise_for_status`; the key's restrictions are
        documented on the constructor.
        """
        headers = {
            "X-Algolia-Application-Id": self._app_id,
            "X-Algolia-API-Key": self._api_key,
        }
        response = requests.post(
            self._query_url, json=body, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()
        return response.json()

    def discover_batches(self) -> list[str]:
        """Discover the current set of `batch` facet values.

        Standard Algolia facet-count query (`hitsPerPage: 0` returns facet
        counts with no hit rows). Plain pagination and `browse` cannot reach
        the full ~6200-record directory (confirmed live, 1000-hit ceiling), so
        the caller must split per-batch instead of paginating. See
        architecture-notes/yc-fetch-plan.md section 2, "Confirmed by a live
        test call" bullets 2-3.
        """
        response = self.query(
            {
                "query": "",
                "facets": ["batch"],
                "hitsPerPage": 0,
                # Algolia's default cap on distinct facet values returned is
                # 100; 1000 is Algolia's own documented maximum for this
                # parameter. YC currently has ~45-50 batch values, but that
                # grows over time, so remove the ceiling risk entirely rather
                # than just raising it.
                "maxValuesPerFacet": 1000,
            }
        )
        return list(response["facets"]["batch"].keys())

    def fetch_batch(self, batch: str) -> list[dict]:
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
        response = self.query(
            {
                "query": "",
                "facetFilters": [[f"batch:{batch}"]],
                "hitsPerPage": ALGOLIA_MAX_HITS_PER_QUERY,
                "page": 0,
            }
        )
        return response["hits"]

    def total_hit_count(self) -> int:
        """Query the directory's true total hit count with a lightweight,
        zero-hit query, for the caller to reconcile the fetched record count
        against.

        `discover_batches` (facet enumeration, capped at `maxValuesPerFacet`
        values, and blind to a record with a missing/null `batch`) and
        `fetch_batch` (each query capped at `ALGOLIA_MAX_HITS_PER_QUERY` hits)
        each have their own silent-truncation failure mode; this gives the
        caller an independent total to compare against so under-fetching is at
        least detectable. See architecture-notes/yc-fetch-plan.md section 2.
        """
        response = self.query({"query": "", "hitsPerPage": 0})
        return response["nbHits"]
