"""Real-Postgres coverage for the EU-Startups tracking-field upgrade."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.postgres_harness import SCHEMA_DIR, SCHEMA_FILES

_MIGRATION = SCHEMA_DIR / "silver-eu-startups-tracking-fields.sql"
_EXPECTED_COLUMNS = (
    ("eu_startups_listings", "founded"),
    ("eu_startups_listings", "total_funding"),
    ("eu_startups_listings", "company_status"),
    ("resolved_signals", "founded"),
    ("resolved_signals", "total_funding"),
)


def _url_for_dbname(database_url: str, dbname: str) -> str:
    info = conninfo_to_dict(database_url)
    info["dbname"] = dbname
    return make_conninfo(**info)


@contextlib.contextmanager
def _scratch_database(database_url: str) -> Iterator[str]:
    name = f"huginn_eu_mig_{uuid.uuid4().hex[:10]}"
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


def _column_shapes(database_url: str) -> tuple[tuple, ...]:
    with psycopg.connect(database_url) as conn:
        return tuple(
            conn.execute(
                "SELECT data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = 'silver' AND table_name = %s "
                "AND column_name = %s",
                (table, column),
            ).fetchone()
            for table, column in _EXPECTED_COLUMNS
        )


def test_upgrade_adds_tracking_fields_idempotently_and_matches_fresh_schema(
    integration_database_url: str,
):
    with _scratch_database(integration_database_url) as url:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(
                "ALTER TABLE silver.eu_startups_listings "
                "DROP COLUMN founded, DROP COLUMN total_funding, "
                "DROP COLUMN company_status"
            )
            conn.execute(
                "ALTER TABLE silver.resolved_signals "
                "DROP COLUMN founded, DROP COLUMN total_funding"
            )
            conn.execute(_MIGRATION.read_text())
            upgraded_shapes = _column_shapes(url)
            conn.execute(_MIGRATION.read_text())

        assert _column_shapes(url) == upgraded_shapes
        assert all(shape is not None for shape in upgraded_shapes)
        assert upgraded_shapes == _column_shapes(integration_database_url)
