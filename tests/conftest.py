"""Shared pytest fixtures for the whole suite. See CLAUDE.md code standard
4 and Jira KAN-52.
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _database_reachable(database_url: str | None) -> bool:
    if not database_url:
        return False
    try:
        with psycopg.connect(database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "db" / "schema"
_SCHEMA_FILES = (
    "00_extensions.sql",
    "ops.sql",
    "bronze.sql",
    "silver.sql",
    "gold.sql",
    "operational.sql",
)
"""Same order as .github/workflows/ci.yml's "Apply database schema" step:
extensions before any table, then dependency order (operational
references gold; the rest reference nothing outside their own schema).
"""

_container = None


def pytest_configure(config) -> None:
    """Must run before collection (HUGINN_DATABASE_URL needs to already be
    set when each integration test module's own skip check fires) and must
    never raise: an uncaught exception here aborts the whole pytest run,
    not just the integration tests this is meant to make optional.
    """
    global _container
    if _database_reachable(os.environ.get("HUGINN_DATABASE_URL")):
        return

    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:
        logger.warning(
            "testcontainers not installed (uv sync should have installed "
            "the dev group); integration tests will skip"
        )
        return

    container = None
    try:
        container = PostgresContainer(
            "postgres:16-alpine",
            username="postgres",
            password="huginn",
            dbname="huginn",
            driver=None,
        )
        container.start()
    except Exception as exc:
        # Construction itself (not just start()) can fail, e.g. if the
        # Docker client can't be initialized — guard the whole thing, not
        # just start(), and only attempt cleanup if construction actually
        # produced a container to stop.
        if container is not None:
            with contextlib.suppress(Exception):
                container.stop()
        logger.warning(
            "testcontainers: could not start a Postgres container, "
            "integration tests will skip: %s",
            exc,
        )
        return

    database_url = container.get_connection_url()

    try:
        with psycopg.connect(database_url, autocommit=True) as conn:
            for filename in _SCHEMA_FILES:
                conn.execute((_SCHEMA_DIR / filename).read_text())
    except Exception as exc:
        with contextlib.suppress(Exception):
            container.stop()
        logger.warning(
            "testcontainers: could not apply db/schema/*.sql, "
            "integration tests will skip: %s",
            exc,
        )
        return

    _container = container
    os.environ["HUGINN_DATABASE_URL"] = database_url


def pytest_unconfigure(config) -> None:
    if _container is not None:
        with contextlib.suppress(Exception):
            _container.stop()
