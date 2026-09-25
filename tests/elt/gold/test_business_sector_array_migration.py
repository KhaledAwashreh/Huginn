"""Live-Postgres coverage for db/schema/gold-business-sector-array.sql.

Two of this migration's failure modes are invisible to a test that only asks
whether the column is text[] at the end:

1. The re-run bug this file exists for. Re-applying `ARRAY[business_sector]`
   to a column that already holds text[] wraps every value one dimension
   deeper. Postgres raises nothing, the type stays text[], and
   cardinality() still returns 2, so the corruption only surfaces as a
   dimension mismatch or a false 'sector changed' in the Type 2 history
   path. It happened for real on 6,204 populated live rows, which is why the
   assertions below check array_ndims and the literal value, not just the
   type.

2. NULL collapsing to '{}'. An empty array reads as "known to have no
   sectors"; NULL reads as "not classified yet". The migration has to keep
   those apart.

Each test builds a throwaway database rather than touching the one it was
given, because producing the pre-migration state means narrowing a real
column back to TEXT. The server those scratch databases are created on is
the throwaway Postgres from tests/conftest.py, so a stray CREATE or DROP
cannot reach a developer's own server.

Runs against the throwaway Postgres that tests/conftest.py provisions,
skipped when testcontainers or Docker is unavailable.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "db" / "schema"
_MIGRATION = _SCHEMA_DIR / "gold-business-sector-array.sql"


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


def _build_pre_migration_schema(db_url: str) -> None:
    """Build the schema as it was before this widening, with the same tables.

    Applies the current gold.sql and then narrows the two columns back to
    TEXT, which is the state an existing deployment is actually in.
    """
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute((_SCHEMA_DIR / "gold.sql").read_text())
        conn.execute("ALTER TABLE gold.company ALTER COLUMN business_sector TYPE TEXT")
        conn.execute(
            "ALTER TABLE gold.company_history ALTER COLUMN business_sector TYPE TEXT"
        )


def _apply_migration(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(_MIGRATION.read_text())


def _insert_scalar_company(db_url: str, name: str, sector: str | None) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gold.company (domain, name, business_sector) "
            "VALUES (%s, %s, %s)",
            (f"{name.lower()}.example", name, sector),
        )


def _read_sectors(db_url: str) -> list[tuple[str | None, list[str] | None, int | None]]:
    """Return (name, business_sector, array_ndims) for every company."""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, business_sector, array_ndims(business_sector) "
            "FROM gold.company ORDER BY name"
        )
        return cur.fetchall()


def _column_type(db_url: str, table: str) -> str:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'gold' AND table_name = %s "
            "AND column_name = 'business_sector'",
            (table,),
        )
        return cur.fetchone()[0]


def test_scalar_becomes_a_one_element_array(
    integration_database_url: str,
):
    with _scratch_database(integration_database_url) as db_url:
        _build_pre_migration_schema(db_url)
        _insert_scalar_company(db_url, "Acme", "Fintech")

        _apply_migration(db_url)

        assert _read_sectors(db_url) == [("Acme", ["Fintech"], 1)]


def test_null_stays_null_and_not_an_empty_array(
    integration_database_url: str,
):
    """'Known to have no sectors' and 'not classified yet' are different
    claims, and only the second one is true of an unclassified company.
    """
    with _scratch_database(integration_database_url) as db_url:
        _build_pre_migration_schema(db_url)
        _insert_scalar_company(db_url, "Acme", None)

        _apply_migration(db_url)

        assert _read_sectors(db_url) == [("Acme", None, None)]


def test_both_tables_widen_to_an_array_type(
    integration_database_url: str,
):
    with _scratch_database(integration_database_url) as db_url:
        _build_pre_migration_schema(db_url)

        _apply_migration(db_url)

        assert _column_type(db_url, "company") == "ARRAY"
        assert _column_type(db_url, "company_history") == "ARRAY"


def test_rerun_on_populated_arrays_changes_nothing(
    integration_database_url: str,
):
    """The regression this migration was silently failing.

    Asserts the value and its dimension count, because both the old
    single-subscript flatten and the original wrapping bug leave the column
    looking like text[] with a plausible cardinality.
    """
    with _scratch_database(integration_database_url) as db_url:
        _build_pre_migration_schema(db_url)
        _insert_scalar_company(db_url, "Acme", "Fintech")
        _apply_migration(db_url)
        before = _read_sectors(db_url)

        _apply_migration(db_url)

        assert _read_sectors(db_url) == before


def test_rerun_keeps_a_multi_valued_array_one_dimension_deep(
    integration_database_url: str,
):
    """The one-element case above is not sufficient on its own: a
    multi-valued array is what actually gets wrapped.
    """
    with _scratch_database(integration_database_url) as db_url:
        with psycopg.connect(db_url, autocommit=True) as conn:
            conn.execute((_SCHEMA_DIR / "gold.sql").read_text())
            conn.execute(
                "INSERT INTO gold.company (domain, name, business_sector) "
                "VALUES ('acme.example', 'Acme', ARRAY['B2B', 'Fintech'])"
            )
        expected = _read_sectors(db_url)

        _apply_migration(db_url)
        _apply_migration(db_url)

        assert _read_sectors(db_url) == expected
        assert expected[0][1] == ["B2B", "Fintech"]
        assert expected[0][2] == 1
