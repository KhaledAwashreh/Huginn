"""Postgres-backed RawStorePort for bronze.api_ingest. See architecture
document section 4.1 point 4 (skip-on-hash-match write) and ADR-0005
(logging required from day one).

Only bronze.api_ingest is wired here (Jira KAN-32). web_scrape_ingest and
newsletter_ingest get the same write path once a mechanism using them
exists; no adapter needs it yet.
"""

from __future__ import annotations

import logging

from huginn.ingestion.ports import RawRecord

logger = logging.getLogger(__name__)

ACTION_WRITE = "write"
ACTION_SKIP = "skip"


def decide_write_action(existing_hash: str | None, new_hash: str) -> str:
    """Decide whether a record needs a write (fresh insert or
    hash-changed overwrite) or only a last_checked_at touch.

    See architecture document section 4.1 point 4 and this plan's Global
    Constraint 3: no existing row, or an existing row whose content_hash
    differs, both write; a matching hash only touches last_checked_at.
    Pure decision logic, no I/O (CLAUDE.md code standard 4).
    """
    if existing_hash is None or existing_hash != new_hash:
        return ACTION_WRITE
    return ACTION_SKIP
