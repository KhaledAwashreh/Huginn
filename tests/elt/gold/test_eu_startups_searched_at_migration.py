"""Live-Postgres coverage for db/schema/gold-eu-startups-searched-at.sql.

The commit that added `gold.company.eu_startups_searched_at` changed
db/schema/gold.sql, the fresh-install path, and shipped no ALTER for a
database that already existed. Per db/schema/README.md that is the defect
this file exists for: without an ALTER the column exists only for new
installs, and the reader in
`src/huginn/elt/gold/repositories/company_repository.py` raises
psycopg.errors.UndefinedColumn against every pre-existing deployment.

The test that matters most is the parity one. An ALTER that adds a column
of a subtly different type, nullability or default than gold.sql declares
produces a schema where the fresh-install path and the upgrade path
disagree, and both are self-consistent, so only a direct comparison finds
it. The two smaller tests pin the upgrade path and idempotency, which is
the claim db/schema/README.md makes about all of these files.

Each test builds a throwaway database rather than touching the one it was
given. The server those scratch databases are created on is the throwaway
Postgres from tests/conftest.py, so a stray CREATE or DROP cannot reach a
developer's own server.

Runs against the throwaway Postgres that tests/conftest.py provisions,
fails rather than skips when testcontainers or Docker is unavailable (tests/conftest.py explains why).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.postgres_harness import SCHEMA_DIR, SCHEMA_FILES

_MIGRATION = SCHEMA_DIR / "gold-eu-startups-searched-at.sql"

_COLUMN = "eu_startups_searched_at"

_TYPE_QUERY = """
SELECT data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'gold' AND table_name = 'company' AND column_name = %s
"""


def _url_for_dbname(database_url: str, dbname: str) -> str:
    """Return database_url pointed at a different database on the same server."""
    info = conninfo_to_dict(database_url)
    info["dbname"] = dbname
    return make_conninfo(**info)


@contextlib.contextmanager
def _scratch_database(database_url: str) -> Iterator[str]:
    """Yield a connection URL to a database holding the base schema, then drop it.

    autocommit is required: CREATE DATABASE cannot run inside a transaction
    block, and psycopg opens an implicit one otherwise.
    """
    name = f"huginn_migtest_{uuid.uuid4().hex[:10]}"
    admin_url = _url_for_dbname(database_url, "postgres")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        url = _url_for_dbname(database_url, name)
        with psycopg.connect(url, autocommit=True) as conn:
            for filename in SCHEMA_FILES:
                conn.execute((SCHEMA_DIR / filename).read_text())
        yield url
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as conn,
        ):
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@contextlib.contextmanager
def _pre_migration_database(database_url: str) -> Iterator[str]:
    """Yield a database whose gold.company predates this column.

    Produced by dropping the column from a base-schema build, which is how
    the sibling migration test reconstructs a pre-ALTER state. Dropping is
    destructive, which is why it happens in a scratch database.
    """
    with _scratch_database(database_url) as url:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f"ALTER TABLE gold.company DROP COLUMN {_COLUMN}")
        yield url


def _column_shape(database_url: str) -> tuple:
    with psycopg.connect(database_url) as conn:
        return conn.execute(_TYPE_QUERY, (_COLUMN,)).fetchone()


def test_the_migration_adds_the_column_to_an_existing_database(
    integration_database_url: str,
):
    """A database created before this column existed must gain it.

    This is the upgrade path itself. Without it the column is a
    fresh-install-only change and every existing deployment keeps the old
    shape, which is exactly what db/schema/README.md forbids.
    """
    with _pre_migration_database(integration_database_url) as url:
        with psycopg.connect(url) as conn:
            present = conn.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'gold' AND table_name = 'company' "
                "AND column_name = %s",
                (_COLUMN,),
            ).fetchone()
        assert present is None, "precondition broken: the column was not dropped"

        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(_MIGRATION.read_text())

        assert _column_shape(url) is not None, (
            f"the migration did not add gold.company.{_COLUMN}, so a database "
            "created before this column existed stays broken"
        )


def test_the_migration_is_idempotent(integration_database_url: str):
    """Re-running it on a database it has already been applied to is a no-op.

    db/schema/README.md promises this of every ALTER file, and the
    consequence of the promise not holding is that applying them in the
    wrong order, or applying one twice during an incident, fails the
    upgrade outright.
    """
    with _pre_migration_database(integration_database_url) as url:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(_MIGRATION.read_text())
            first = _column_shape(url)
            conn.execute(_MIGRATION.read_text())

        assert _column_shape(url) == first, (
            "re-applying the migration changed the column, so it is not "
            "idempotent and re-running an upgrade is not safe"
        )


def test_the_migration_agrees_with_the_fresh_install_path(
    integration_database_url: str,
):
    """The upgraded column must be identical to the one gold.sql declares.

    An ALTER can add a column of a different type, nullability, or default
    than the fresh-install path and leave both paths self-consistent, so
    only a direct comparison between the two detects it. The repository
    reads this column on every EU-Startups candidate query, so a mismatch
    surfaces as a type error at read time rather than at migration time.
    """
    with (
        _scratch_database(integration_database_url) as fresh_url,
        _pre_migration_database(integration_database_url) as upgraded_url,
    ):
        with psycopg.connect(upgraded_url, autocommit=True) as conn:
            conn.execute(_MIGRATION.read_text())

        assert _column_shape(upgraded_url) == _column_shape(fresh_url), (
            "the upgraded column differs from the fresh-install one, so a "
            "migrated database and a new one disagree about the same "
            "column and code that works on one fails on the other"
        )
