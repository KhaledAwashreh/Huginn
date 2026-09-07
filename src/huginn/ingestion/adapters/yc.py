"""YC directory adapter. See architecture document section 5.

No official API. Queries the public, search-only Algolia key exposed in
the directory's frontend JS directly, rather than parsing rendered pages.
Mechanism: "api" (a direct structured query, not HTML scraping).

Open risk, not yet resolved: YC's Terms of Service explicitly prohibit
scraping and data-mining, while robots.txt says nothing about querying
the Algolia backend directly. See Jira KAN-7 and `docs/sources/yc-directory.md`.
Do not ship this adapter's real implementation until KAN-7 is closed.
"""

from __future__ import annotations

from huginn.ingestion.ports import RawRecord


class YcDirectoryAdapter:
    source = "yc"
    mechanism = "api"

    def fetch(self) -> list[RawRecord]:
        """TODO (KAN-21, blocked on KAN-7): query YC's Algolia index directly
        with the frontend's search-only app ID and API key.
        """
        raise NotImplementedError
