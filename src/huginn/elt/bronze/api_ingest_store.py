"""RawStorePort for bronze.api_ingest. See architecture document
section 4.1 point 4 (skip-on-hash-match write) and ADR-0005 (logging
required from day one).

Orchestration only: this module decides *what* should happen to each
record and delegates every read and write to an injected
`ApiIngestRepositoryPort`. No SQL and no `psycopg` import lives here;
both belong to `huginn.elt.bronze.repositories.api_ingest_repository`.

Only bronze.api_ingest is wired here (Jira KAN-32). web_scrape_ingest and
newsletter_ingest get the same write path once a mechanism using them
exists; no adapter needs it yet.
"""

from __future__ import annotations

import logging
import uuid

from huginn.elt.bronze.ports import ApiIngestRepositoryPort
from huginn.elt.bronze.watermark import compute_content_hash
from huginn.elt.ingestion.models import RawRecord

logger = logging.getLogger(__name__)

ACTION_WRITE = "write"
ACTION_SKIP = "skip"


def decide_write_action(existing_hash: str | None, new_hash: str) -> str:
    """Decide whether a record needs a write (fresh insert or
    hash-changed overwrite) or only a last_checked_at touch.

    See architecture document section 4.1 point 4 and docs/superpowers/plans/
    2026-09-08-kan-32-raw-store-port.md's Global Constraint 3: no existing row, or an existing row whose content_hash
    differs, both write; a matching hash only touches last_checked_at.
    Pure decision logic, no I/O (CLAUDE.md code standard 4).
    """
    if existing_hash is None or existing_hash != new_hash:
        return ACTION_WRITE
    return ACTION_SKIP


class PostgresApiIngestStore:
    """`RawStorePort` implementation against `bronze.api_ingest` only. See
    architecture document section 4.1 point 4 and docs/superpowers/plans/
    2026-09-08-kan-32-raw-store-port.md's Global Constraint 3 (upsert semantics) and Constraint 4 (stable_fields choice).

    Takes an `ApiIngestRepositoryPort` rather than a database URL: the
    hash lookup this class needs is the same read `StatePort` exposes, and
    routing both through one repository keeps that query defined once.
    """

    def __init__(self, repository: ApiIngestRepositoryPort) -> None:
        self._repository = repository

    def write(
        self, source: str, mechanism: str, records: list[RawRecord], run_id: str
    ) -> int:
        """See huginn.elt.bronze.ports.RawStorePort.write. Only mechanism
        "api" is handled (Jira KAN-32 scope; see docs/superpowers/plans/
        2026-09-08-kan-32-raw-store-port.md, Global Constraint 5). Returns
        the count actually written, excluding hash-match skips.
        """
        if mechanism != "api":
            raise NotImplementedError(
                f"PostgresApiIngestStore only writes bronze.api_ingest "
                f"('api' mechanism); got mechanism={mechanism!r}. "
                f"web_scrape_ingest and newsletter_ingest are out of scope "
                f"for KAN-32."
            )

        try:
            uuid.UUID(run_id)
        except ValueError as exc:
            raise ValueError(
                f"run_id must be a valid UUID string; got {run_id!r}"
            ) from exc

        written = 0
        skipped = 0
        # One `with` around the whole loop, not one per record: every
        # statement for this call shares a single connection and commits as
        # one transaction, so a large run costs one connect rather than two
        # per record, and a mid-loop failure leaves no partial batch behind.
        with self._repository:
            for record in records:
                content_hash = compute_content_hash(
                    record.payload, sorted(record.payload.keys())
                )
                existing_hash = self._repository.lookup_hash(source, record.stable_id)

                if decide_write_action(existing_hash, content_hash) == ACTION_WRITE:
                    self._repository.write(
                        source,
                        record.stable_id,
                        record.payload,
                        content_hash,
                        run_id,
                    )
                    written += 1
                else:
                    self._repository.touch(source, record.stable_id)
                    skipped += 1

        logger.info(
            "bronze.api_ingest write source=%s run_id=%s: %d written, %d skipped",
            source,
            run_id,
            written,
            skipped,
        )
        return written
