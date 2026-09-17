from pathlib import Path

import psycopg

from huginn.management.database import PostgresReadiness

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "db" / "schema"
SCHEMA_FILES = (
    "00_extensions.sql",
    "ops.sql",
    "bronze.sql",
    "silver.sql",
    "gold.sql",
    "operational.sql",
)


def test_ready_requires_bootstrapped_tables(
    management_database_url,
    empty_management_database_url,
):
    assert PostgresReadiness(management_database_url).is_ready() is True
    assert PostgresReadiness(empty_management_database_url).is_ready() is False


def test_ready_detects_missing_required_column(empty_management_database_url):
    with psycopg.connect(empty_management_database_url, autocommit=True) as conn:
        for filename in SCHEMA_FILES:
            conn.execute((SCHEMA_DIR / filename).read_text())

    readiness = PostgresReadiness(empty_management_database_url)
    assert readiness.is_ready() is True

    with psycopg.connect(empty_management_database_url) as conn:
        conn.execute(
            "ALTER TABLE operational.users RENAME COLUMN email TO legacy_email"
        )
        conn.commit()

    assert readiness.is_ready() is False
