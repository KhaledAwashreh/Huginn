"""HN "Who's Hiring" adapter. See architecture document section 5.

Official Firebase API, no auth, no rate limit. Mechanism: "api".
"""

from __future__ import annotations

from huginn.ingestion.ports import RawRecord

FIREBASE_BASE_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNewsAdapter:
    source = "hn"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """Fetch the current "Who's Hiring" thread and its top-level comments.

        TODO (KAN-21): find the current month's "Who's Hiring" story ID,
        fetch its child comment IDs, then fetch each comment's item JSON.
        ~11% of sampled posts have no extractable URL (see
        `sources/hn-who-is-hiring.md`), which downstream entity resolution
        already accounts for by falling back to fuzzy name matching.
        """
        raise NotImplementedError
