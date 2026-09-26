import psycopg

from huginn.management.database import PostgresReadiness
from tests.postgres_harness import SCHEMA_DIR, SCHEMA_FILES


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
