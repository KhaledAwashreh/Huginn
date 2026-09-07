"""HN "Who's Hiring" adapter. See architecture document section 5.

Official Firebase API, no auth, no rate limit. Mechanism: "api".
Fetch-plan decisions: architecture-notes/hn-fetch-plan.md (KAN-38).
"""

from __future__ import annotations

import re

import requests

from huginn.ingestion.ports import RawRecord

FIREBASE_BASE_URL = "https://hacker-news.firebaseio.com/v0"
REQUEST_TIMEOUT_SECONDS = 10.0

WHOISHIRING_USER = "whoishiring"
THREAD_TITLE_PATTERN = re.compile(r"^Ask HN: Who is hiring\? \(")


def _get_json(url: str) -> dict | None:
    """GET a Firebase URL and return its parsed JSON body.

    A genuine request failure (timeout, non-2xx, malformed JSON) raises; a
    body of the JSON literal `null` returns `None`. See
    architecture-notes/hn-fetch-plan.md section 2.
    """
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _discover_thread_item() -> dict:
    """Find and return the current "Who's Hiring" root thread item.

    `submitted[0]` plus a title check, no Algolia cross-check. See
    architecture-notes/hn-fetch-plan.md section 1.
    """
    user = _get_json(f"{FIREBASE_BASE_URL}/user/{WHOISHIRING_USER}.json")
    candidate_id = user["submitted"][0]
    item = _get_json(f"{FIREBASE_BASE_URL}/item/{candidate_id}.json")
    title = item.get("title", "") if item else ""
    if not THREAD_TITLE_PATTERN.match(title):
        raise RuntimeError(
            f"whoishiring's latest submission (id {candidate_id}) does not "
            f"look like a Who's Hiring thread (title: {title!r})"
        )
    return item


class HackerNewsAdapter:
    source = "hn"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """Fetch the current "Who's Hiring" thread and its top-level comments.

        TODO (KAN-29, Task 2/3): thread discovery and kid fetching not yet
        implemented.
        """
        raise NotImplementedError
