"""Shared pytest fixtures for the whole suite. See CLAUDE.md code standard
4 (DB-free unit tests everywhere feasible; live-Postgres integration
tests gated on HUGINN_DATABASE_URL) and Jira KAN-52.

If HUGINN_DATABASE_URL isn't already set to something reachable (by
`.env`, a real env var, or CI's own Postgres service — see
.github/workflows/ci.yml), starts a throwaway Postgres testcontainer,
applies db/schema/*.sql, and exports its connection string for the rest
of the session. Checking reachability, not just presence, matters: `.env`
commonly carries a HUGINN_DATABASE_URL pointing at a database that isn't
actually running (e.g. from a prior session), and treating that as
"already configured" would silently skip every integration test instead
of falling back to a container. Every existing tests/**/*_integration.py
file already reads HUGINN_DATABASE_URL from the environment at import
time and skips cleanly if it's unset or unreachable, so this needs no
changes there: it just makes that check usually succeed instead of
usually skip, locally.

If Docker isn't available, or anything here fails, this falls back to
that same skip behavior rather than failing the run: a convenience, not
a new hard requirement. Every failure path below is deliberately caught,
not just the container-start step, since pytest_configure runs inside
pytest's own session setup — an uncaught exception here aborts the whole
pytest invocation (including plain DB-free unit test runs), not just the
integration tests this module is trying to make optional.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()


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
    """Runs before test collection, so HUGINN_DATABASE_URL is already set
    (or not) by the time each integration test module's own module-level
    skip check runs at import time.
    """
    global _container
    if _database_reachable(os.environ.get("HUGINN_DATABASE_URL")):
        return

    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:
        print(
            "\n(testcontainers not installed (uv sync should have installed "
            "the dev group), integration tests will skip)"
        )
        return

    container = PostgresContainer(
        "postgres:16-alpine",
        username="postgres",
        password="huginn",
        dbname="huginn",
        driver=None,
    )
    try:
        container.start()
    except Exception as exc:
        # start() can fail after Docker has already created and started
        # the container (e.g. the internal psql readiness wait times out),
        # so it may need stopping even though it never got far enough to
        # become `_container`. Best-effort: a failure here must not mask
        # the original exception below.
        with contextlib.suppress(Exception):
            container.stop()
        print(
            f"\n(testcontainers: could not start a Postgres container, "
            f"integration tests will skip: {exc})"
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
        print(
            f"\n(testcontainers: could not apply db/schema/*.sql, "
            f"integration tests will skip: {exc})"
        )
        return

    _container = container
    os.environ["HUGINN_DATABASE_URL"] = database_url


def pytest_unconfigure(config) -> None:
    if _container is not None:
        with contextlib.suppress(Exception):
            _container.stop()
