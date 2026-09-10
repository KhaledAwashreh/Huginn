"""HN staging loader: bronze.api_ingest (source="hn") -> silver.hn_postings.
See architecture document section 4.2, ADR-0001, docs/entities.md's
HnPostingStaging. Jira KAN-34.

Every comment in the "Who's Hiring" thread is a hiring signal by
construction (the thread's entire premise): signal_type is always
"hiring", there is no per-comment classification to do or data to do it
from. Field-mapping and edge cases below are grounded in the live thread
(this plan's Task 2 "Grounding" note), not assumed.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from huginn.silver.ports import HnStagingRepositoryPort

logger = logging.getLogger(__name__)

_HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"

_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'<a\s+href="([^"]+)"', re.IGNORECASE)
_LINK_REMOVE_RE = re.compile(r"<a\s[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class HnPostingStaging:
    """One row of silver.hn_postings. See docs/entities.md's HnPostingStaging."""

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str


def _clean_text(fragment: str) -> str:
    """Strip HTML tags, unescape entities, collapse whitespace. HN's
    `text` is Firebase-escaped HTML with literal `<p>` breaks and no
    closing tag (confirmed live, this plan's Task 2).
    """
    unescaped = html.unescape(fragment)
    stripped = _TAG_RE.sub(" ", unescaped)
    return " ".join(stripped.split())


def parse_hn_posting(payload: dict) -> HnPostingStaging | None:
    """Parse one HN Firebase item, or return None if it is not a postable
    comment: the thread's root "story" item, or a deleted comment with no
    `text` (both confirmed present live, this plan's Task 2).

    Convention (confirmed live, not universal): the header, up to the
    first literal `<p>`, is `|`-separated; field 0 is the company name;
    an `<a href="...">` wherever it appears in the header is the
    company's website. A header with no `|` (confirmed live: meta-
    comments and non-standard postings) becomes company_name_raw as-is;
    with no website recoverable either, it fails Task 6's domain match
    and correctly lands in Task 7's manual-review queue rather than
    being dropped or given a fabricated identity.
    """
    if payload.get("type") != "comment":
        return None
    text = payload.get("text")
    if not text:
        return None

    if "<p>" in text:
        header, _, rest = text.partition("<p>")
    else:
        header, rest = text, ""

    fields = [field.strip() for field in header.split("|")]
    company_name_raw = _clean_text(_LINK_REMOVE_RE.sub(" ", fields[0]))

    href_match = _HREF_RE.search(header)
    website = html.unescape(href_match.group(1)) if href_match else None

    return HnPostingStaging(
        stable_id=str(payload["id"]),
        company_name_raw=company_name_raw,
        website=website,
        signal_type="hiring",
        stage=None,
        description=_clean_text(rest),
        occurred_on=datetime.fromtimestamp(payload["time"], tz=UTC),
        url=_HN_ITEM_URL.format(id=payload["id"]),
    )


class HnStagingLoader:
    """Reads bronze.api_ingest (source="hn") and upserts silver.hn_postings
    via its injected port. See docs/entities.md's HnPostingStaging and
    ADR-0001. Jira KAN-34. See huginn.silver.ports for the port
    contract; this class holds no persistence detail of its own.

    Reads every bronze row for the source each run rather than tracking
    its own watermark: silver.hn_postings' UNIQUE(stable_id) upsert
    already makes re-processing idempotent, mirroring Bronze's own
    hash-based idempotency (architecture document section 4.1). The
    upsert still writes every row on every run; it is the resulting
    database state, not the work done, that is unchanged.
    """

    def __init__(self, repository: HnStagingRepositoryPort) -> None:
        self._repository = repository

    def load(self) -> int:
        """Parse and upsert every current HN bronze row, returning the
        count of rows upserted (always equals the count of parseable
        bronze rows, excluding skipped non-comment/deleted ones; the
        write executes on every row even when nothing changed).
        """
        # See huginn.silver.ports's module docstring for why this whole
        # method shares one `with self._repository:` scope.
        with self._repository:
            payloads = self._repository.read("hn")
            written = 0
            for payload in payloads:
                staging_row = parse_hn_posting(payload)
                if staging_row is None:
                    continue
                self._repository.upsert(staging_row)
                written += 1

        logger.info(
            "silver.hn_postings load: %d written (of %d bronze rows)",
            written,
            len(payloads),
        )
        return written
