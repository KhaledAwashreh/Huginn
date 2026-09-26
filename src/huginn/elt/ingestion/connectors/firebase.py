"""Firebase client for HN's public API. See architecture document section 5
and architecture-notes/hn-fetch-plan.md (KAN-38).

No auth and no rate limit, so this connector takes no credentials. Unlike
`algolia.py` there is nothing per-consumer to inject: the public Firebase REST
API has exactly one address, so `FIREBASE_BASE_URL` is a constant here rather
than a constructor argument. Which user to read and which thread counts as the
current one is HN's own policy and stays in the adapter.
"""

from __future__ import annotations

import requests

FIREBASE_BASE_URL = "https://hacker-news.firebaseio.com/v0"
DEFAULT_TIMEOUT_SECONDS = 10.0


class FirebaseConnector:
    """Read-only client for the public Firebase REST API.

    Stateless by design. The HN adapter calls `get_item` concurrently from a
    `ThreadPoolExecutor` with several workers on a single shared instance
    (ADR-0003), so this deliberately uses module-level `requests.get` rather
    than a `requests.Session`, which is documented as not thread-safe. A
    connection-pooling `Session` here would be a bug that only surfaces under
    concurrency; thread-local sessions would be the fix if pooling is ever
    wanted.
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Capture the request timeout. No credentials: the API is public."""
        self._timeout = timeout

    def get_user(self, user_id: str) -> dict | None:
        """Return one user's profile, or `None` if the body is a bare `null`.

        Returns `None` for a bare `null` response (the id never existed); a
        genuine request failure (timeout, non-2xx, malformed JSON) raises. See
        architecture-notes/hn-fetch-plan.md section 2.
        """
        return self._get_json(f"user/{user_id}.json")

    def get_item(self, item_id: int) -> dict | None:
        """Return one HN item by id.

        Returns `None` for a bare `null` response (id never existed); a
        `deleted: true` stub is returned as-is like any other item. See
        architecture-notes/hn-fetch-plan.md section 2.
        """
        return self._get_json(f"item/{item_id}.json")

    def _get_json(self, path: str) -> dict | None:
        """GET one path under `FIREBASE_BASE_URL` and return its parsed body.

        A genuine request failure (timeout, non-2xx, malformed JSON) raises; a
        body of the JSON literal `null` returns `None`. See
        architecture-notes/hn-fetch-plan.md section 2.
        """
        response = requests.get(f"{FIREBASE_BASE_URL}/{path}", timeout=self._timeout)
        response.raise_for_status()
        return response.json()
