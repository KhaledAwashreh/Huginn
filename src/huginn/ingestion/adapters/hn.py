"""HN "Who's Hiring" adapter. See architecture document section 5.

Official Firebase API, no auth, no rate limit. Mechanism: "api".
Fetch-plan decisions: architecture-notes/hn-fetch-plan.md (KAN-38).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import requests

from huginn.ingestion.ports import ApiSourcePort, RawRecord

FIREBASE_BASE_URL = "https://hacker-news.firebaseio.com/v0"
REQUEST_TIMEOUT_SECONDS = 10.0

WHOISHIRING_USER = "whoishiring"
THREAD_TITLE_PATTERN = re.compile(r"^Ask HN: Who is hiring\? \(")
MAX_CONCURRENT_FETCHES = 8


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


def _fetch_item(item_id: int) -> dict | None:
    """Fetch one HN item by id.

    Returns `None` for a bare `null` response (id never existed); a
    `deleted: true` stub is returned as-is like any other item. See
    architecture-notes/hn-fetch-plan.md section 2.
    """
    return _get_json(f"{FIREBASE_BASE_URL}/item/{item_id}.json")


class HackerNewsAdapter(ApiSourcePort):
    source = "hn"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """Fetch the current "Who's Hiring" thread and its top-level comments.

        Root plus direct kids only, no nested-reply walk; kids are fetched
        with bounded concurrency. See architecture-notes/hn-fetch-plan.md
        section 2.
        """
        root_item = _discover_thread_item()
        records = [RawRecord(stable_id=str(root_item["id"]), payload=root_item)]

        kid_ids = root_item.get("kids", [])
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES) as executor:
            kid_items = list(executor.map(_fetch_item, kid_ids))

        for kid_item in kid_items:
            if kid_item is None:
                continue
            records.append(RawRecord(stable_id=str(kid_item["id"]), payload=kid_item))

        return records
