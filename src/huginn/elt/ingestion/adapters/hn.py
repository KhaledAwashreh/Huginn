"""HN "Who's Hiring" adapter. See architecture document section 5.

Official Firebase API, no auth, no rate limit. Mechanism: "api".
The client itself lives in `huginn.elt.ingestion.connectors.firebase` and is
injected; this module holds only HN's own ingestion policy.
Fetch-plan decisions: architecture-notes/hn-fetch-plan.md (KAN-38).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from huginn.elt.ingestion.connectors.firebase import FirebaseConnector
from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import ApiSourcePort

WHOISHIRING_USER = "whoishiring"
THREAD_TITLE_PATTERN = re.compile(r"^Ask HN: Who is hiring\? \(")
MAX_CONCURRENT_FETCHES = 8


class HackerNewsAdapter(ApiSourcePort):
    source = "hn"
    mechanism = "api"

    def __init__(self, firebase: FirebaseConnector) -> None:
        """Receive the Firebase client. Required rather than defaulted so the
        adapter cannot reach the network except through an injected client.
        """
        self._firebase = firebase

    def _discover_thread_item(self) -> dict:
        """Find and return the current "Who's Hiring" root thread item.

        `submitted[0]` plus a title check, no Algolia cross-check. See
        architecture-notes/hn-fetch-plan.md section 1.
        """
        user = self._firebase.get_user(WHOISHIRING_USER)
        submitted = user.get("submitted") if user else None
        if not submitted:
            raise RuntimeError(
                f"whoishiring's user profile is null or has no submitted items "
                f"(response: {user!r}); cannot discover the current thread"
            )
        candidate_id = submitted[0]
        item = self._firebase.get_item(candidate_id)
        title = item.get("title", "") if item else ""
        if not THREAD_TITLE_PATTERN.match(title):
            raise RuntimeError(
                f"whoishiring's latest submission (id {candidate_id}) does not "
                f"look like a Who's Hiring thread (title: {title!r})"
            )
        return item

    def fetch(self) -> list[RawRecord]:
        """Fetch the current "Who's Hiring" thread and its top-level comments.

        Root plus direct kids only, no nested-reply walk; kids are fetched
        with bounded concurrency. See architecture-notes/hn-fetch-plan.md
        section 2.
        """
        root_item = self._discover_thread_item()
        records = [RawRecord(stable_id=str(root_item["id"]), payload=root_item)]

        kid_ids = root_item.get("kids", [])
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES) as executor:
            kid_items = list(executor.map(self._firebase.get_item, kid_ids))

        for kid_item in kid_items:
            if kid_item is None:
                continue
            records.append(RawRecord(stable_id=str(kid_item["id"]), payload=kid_item))

        return records
