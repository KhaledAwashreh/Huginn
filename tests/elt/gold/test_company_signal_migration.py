"""Live-Postgres coverage for db/schema/gold-company-signal-source-stable-id.sql.

The KAN-41 commit d0f37ab changed only db/schema/gold.sql, the fresh-install
path. It shipped no ALTER for a database that already existed, so the writer
failed with psycopg.errors.UndefinedColumn against any pre-existing
deployment. This file closes that gap and is where the ALTER's own three
distinct starting states are pinned down, because the file's precondition
guard is only correct if it distinguishes them.

Each test builds a throwaway database rather than touching the one it was
given: the pre-ADR state is produced by dropping a column and its dependent
constraint, which is destructive and has no business near real fact rows.
The server those scratch databases are created on is the throwaway Postgres
from tests/conftest.py, so a stray CREATE or DROP cannot reach a
developer's own server.

Runs against the throwaway Postgres that tests/conftest.py provisions,
skipped when testcontainers or Docker is unavailable.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import errors
from psycopg.conninfo import conninfo_to_dict, make_conninfo

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "db" / "schema"
_MIGRATION = _SCHEMA_DIR / "gold-company-signal-source-stable-id.sql"


def _url_for_dbname(database_url: str, dbname: str) -> str:
    """Return database_url pointed at a different database on the same server."""
    info = conninfo_to_dict(database_url)
    info["dbname"] = dbname
    return make_conninfo(**info)


@contextlib.contextmanager
def _scratch_database(database_url: str) -> Iterator[str]:
    """Yield a connection URL to an empty database, then drop it.

    autocommit is required: CREATE DATABASE cannot run inside a transaction
    block, and psycopg opens an implicit one otherwise.
    """
    name = f"huginn_migtest_{uuid.uuid4().hex[:10]}"
    admin_url = _url_for_dbname(database_url, "postgres")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        yield _url_for_dbname(database_url, name)
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as conn,
        ):
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _apply_current_schema(db_url: str) -> None:
    """Build the post-ADR schema exactly as a fresh install produces it."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute((_SCHEMA_DIR / "gold.sql").read_text())


def _revert_to_pre_adr_schema(db_url: str) -> None:
    """Recreate the pre-KAN-41 shape: no source_stable_id, no natural key.

    Dropping the column with CASCADE also drops the unique constraint that
    depends on it, which is precisely the pair of things KAN-41 added, so
    this lands on the old schema without hardcoding a copy of its DDL.
    """
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "ALTER TABLE gold.company_signal DROP COLUMN source_stable_id CASCADE"
        )


def _insert_fact(db_url: str, source: str, source_stable_id: str) -> None:
    """Insert one company plus one fact row keyed by (source, source_stable_id).

    Must run before _revert_to_pre_adr_schema, which drops the very column
    this writes.
    """
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gold.company (domain, name) VALUES (%s, %s) RETURNING id",
            (f"{source_stable_id}.example", source_stable_id),
        )
        conn.execute(
            """
            INSERT INTO gold.company_signal
                (company_id, source, source_stable_id, signal_type, occurred_at)
            SELECT id, %s, %s, 'hiring', now() FROM gold.company
            WHERE domain = %s
            """,
            (source, source_stable_id, f"{source_stable_id}.example"),
        )


def _run_migration(db_url: str) -> None:
    """Apply the migration under test."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(_MIGRATION.read_text())


def _source_stable_id_is_mapped(db_url: str) -> bool:
    """Return whether a NOT NULL source_stable_id column exists."""
    with psycopg.connect(db_url) as conn:
        return bool(
            conn.execute(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_schema = 'gold' AND table_name = 'company_signal'
                  AND column_name = 'source_stable_id' AND is_nullable = 'NO'
                """
            ).fetchone()[0]
            == 1
        )


def _duplicate_fact_is_refused(db_url: str) -> bool:
    """Return whether re-inserting an existing natural key raises."""
    with (
        psycopg.connect(db_url, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        try:
            cur.execute(
                """
                INSERT INTO gold.company_signal
                    (company_id, source, source_stable_id, signal_type, occurred_at)
                SELECT id, 'hn', 'stable-1', 'hiring', now()
                FROM gold.company WHERE domain = 'stable-1.example'
                """
            )
        except errors.UniqueViolation:
            return True
    return False


def test_refuses_to_backfill_pre_adr_rows_that_have_no_key(
    integration_database_url: str,
):
    """Rows predating the column cannot be keyed, so refuse and say how to recover.

    This refusal is the point of the migration's precondition: inventing a
    placeholder would permanently poison the natural key ADR-0007 exists to
    make trustworthy, and gold.company_signal is rebuildable from
    silver.resolved_signals anyway.
    """
    with _scratch_database(integration_database_url) as db_url:
        _apply_current_schema(db_url)
        _insert_fact(db_url, "hn", "stable-1")
        # Dropping the column discards the key with it, which is exactly the
        # pre-ADR state: rows that exist, and a key that does not.
        _revert_to_pre_adr_schema(db_url)

        with pytest.raises(errors.RaiseException) as excinfo:
            _run_migration(db_url)

        assert "TRUNCATE" in str(excinfo.value)


def test_upgrades_an_empty_pre_adr_table(
    integration_database_url: str,
):
    """The real upgrade path: old schema, no rows, nothing to backfill."""
    with _scratch_database(integration_database_url) as db_url:
        _apply_current_schema(db_url)
        _revert_to_pre_adr_schema(db_url)

        _run_migration(db_url)

        assert _source_stable_id_is_mapped(db_url)


def test_rerun_on_a_populated_migrated_table_is_a_noop(
    integration_database_url: str,
):
    """A migrated table that has since collected rows must re-run cleanly.

    The guard keys on the old schema, not on the table being non-empty. Once
    the column exists, every row carries a real source_stable_id, so a re-run
    is an ordinary no-op; refusing here would make the file non-idempotent for
    exactly the database it was written for, since re-running it is what an
    operator does after collecting facts.
    """
    with _scratch_database(integration_database_url) as db_url:
        _apply_current_schema(db_url)
        _insert_fact(db_url, "hn", "stable-1")

        _run_migration(db_url)

        assert _source_stable_id_is_mapped(db_url)
        assert _duplicate_fact_is_refused(db_url)


def test_rerun_on_a_fresh_install_is_a_noop(
    integration_database_url: str,
):
    """Applying the ALTER on top of db/schema/gold.sql changes nothing."""
    with _scratch_database(integration_database_url) as db_url:
        _apply_current_schema(db_url)

        _run_migration(db_url)

        assert _source_stable_id_is_mapped(db_url)
