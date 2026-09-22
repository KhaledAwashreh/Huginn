from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "db" / "schema"
SCHEMA_FILES = (
    "00_extensions.sql",
    "ops.sql",
    "bronze.sql",
    "silver.sql",
    "gold.sql",
    "operational.sql",
)


@pytest.fixture(scope="session")
def management_database_url():
    with PostgresContainer(
        "postgres:16-alpine",
        username="postgres",
        password="huginn",
        dbname="huginn_management_test",
        driver=None,
    ) as container:
        database_url = container.get_connection_url()
        with psycopg.connect(database_url, autocommit=True) as conn:
            for filename in SCHEMA_FILES:
                conn.execute((SCHEMA_DIR / filename).read_text())
        yield database_url


@pytest.fixture
def empty_management_database_url():
    with PostgresContainer(
        "postgres:16-alpine",
        username="postgres",
        password="huginn",
        dbname="huginn_management_empty_test",
        driver=None,
    ) as container:
        yield container.get_connection_url()
