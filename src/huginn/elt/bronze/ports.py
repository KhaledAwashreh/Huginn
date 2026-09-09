"""Port contracts for the Bronze stage. See architecture document
section 4.1 (mechanism-grouped tables, hash-based write behavior) and
section 5 (where these ports sit in the ingestion diagram).

`RawStorePort` and `StatePort` are the outbound contracts ingestion
depends on; they live here rather than in `huginn.elt.ingestion.ports`
because Bronze owns what they mean and what implements them.
`ApiIngestRepositoryPort` is the persistence boundary underneath both:
the single place `bronze.api_ingest` is actually read from and written
to, so a `RawStorePort` implementation and a `StatePort` implementation
share one query rather than each carrying their own copy.
"""

from __future__ import annotations

from typing import Protocol

from huginn.elt.ingestion.models import RawRecord


class RawStorePort(Protocol):
    """Writes fetched records to Bronze. See architecture document section 4.1
    for the mechanism-grouped table layout and the hash-based write behavior.
    """

    def write(
        self, source: str, mechanism: str, records: list[RawRecord], run_id: str
    ) -> int:
        """Write records to the appropriate Bronze table, returning the
        count actually written (inserted or overwritten), excluding
        hash-match skips. `IngestionService` records this count on
        `ops.job_runs.rows_written`; it must not be `len(records)`, since a
        fully-static source correctly writes zero rows every run.

        Implementations must apply the skip-on-hash-match behavior: a
        record whose content hash matches the last stored hash for its
        `(source, stable_id)` should not insert a new row, only bump
        `last_checked_at` on the existing one. A record whose hash differs
        overwrites the existing row in place (Bronze's
        `UNIQUE (source, stable_id)` constraint allows exactly one row per
        entity; no prior version is retained).
        """
        ...


class StatePort(Protocol):
    """Per-entity content-hash watermark, replacing a source-provided cursor.
    See architecture document section 4.1: neither HN's Firebase API nor
    YC's Algolia backend offers a reliable "give me only what changed" cursor.
    """

    def last_hash(self, source: str, stable_id: str) -> str | None:
        """The last stored content hash for this entity, or None if never seen."""
        ...


class ApiIngestRepositoryPort(Protocol):
    """Every read and write against `bronze.api_ingest`, in one contract.

    `RawStorePort`'s write path and `StatePort`'s read both need the same
    "stored content_hash for (source, stable_id)" query. Routing both
    through this port keeps that query defined once, in one repository
    implementation, instead of each class issuing its own copy against the
    same table. Implementations own the SQL and the database connection;
    nothing above this port imports `psycopg`.
    """

    def lookup_hash(self, source: str, stable_id: str) -> str | None:
        """The stored content hash for `(source, stable_id)`, or None if
        no row exists yet.
        """
        ...

    def write(
        self,
        source: str,
        stable_id: str,
        payload: dict,
        content_hash: str,
        run_id: str,
    ) -> None:
        """Upsert one row: a fresh `(source, stable_id)` inserts, an
        existing one overwrites in place. See architecture document
        section 4.1 point 4.
        """
        ...

    def touch(self, source: str, stable_id: str) -> None:
        """Bump `last_checked_at` only, leaving `payload` and
        `content_hash` untouched, for a hash-match skip.
        """
        ...
