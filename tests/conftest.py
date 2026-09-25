"""Shared pytest fixtures for the whole suite. See CLAUDE.md code standard
4 and Jira KAN-52.

The integration database is provisioned here, never discovered. A suite that
falls back to whatever HUGINN_DATABASE_URL happens to name re-runs the whole
pipeline over real dev rows and creates scratch databases on the developer's
own server, so the only URL an integration test ever sees is the one the
fixture below starts.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()
"""Nothing here connects through the developer's URL, so the only reason to
read .env is tests/test_integration_database_isolation.py, which needs the
value to prove the suite is pointed somewhere else. Removing this would
silently disarm that tripwire.
"""

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "db" / "schema"
_SCHEMA_FILES = (
    "00_extensions.sql",
    "ops.sql",
    "bronze.sql",
    "silver.sql",
    "gold.sql",
    "operational.sql",
)
"""Same order as db/schema/README.md's fresh-install command: extensions
before any table, then dependency order (operational references gold; the
rest reference nothing outside their own schema).
"""

_POSTGRES_IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def integration_database_url() -> Iterator[str]:
    """Yield a connection URL to a throwaway Postgres holding the production schema.

    Skips rather than fails when testcontainers or Docker is unavailable, so
    an environment that cannot host a database costs the integration tests
    and nothing else. The alternative failure mode is worse than a skip: a
    suite that quietly falls back to a reachable database runs against
    whatever the developer keeps in it.
    """
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:
        pytest.skip(
            "testcontainers is not installed; run uv sync to install the dev group"
        )

    container = None
    try:
        container = PostgresContainer(
            _POSTGRES_IMAGE,
            username="postgres",
            password="huginn",
            dbname="huginn",
            driver=None,
        )
        container.start()
    except Exception as exc:
        # Construction itself (not just start()) can fail, e.g. if the Docker
        # client can't be initialized, so guard the whole thing and only
        # attempt cleanup if construction produced a container to stop.
        if container is not None:
            with contextlib.suppress(Exception):
                container.stop()
        logger.warning("could not start a Postgres container: %s", exc)
        pytest.skip(f"could not start a Postgres container: {exc}")

    database_url = container.get_connection_url()

    # Unlike the container start above, a failure here is not a reason to
    # skip: Docker and Postgres have both already proven themselves working,
    # so an exception applying db/schema/*.sql means the SQL is broken rather
    # than the environment missing. Swallowing it into a quiet skip would hide
    # a real schema bug behind a false "tests skipped" result.
    try:
        with psycopg.connect(database_url, autocommit=True) as conn:
            for filename in _SCHEMA_FILES:
                conn.execute((_SCHEMA_DIR / filename).read_text())
    except Exception:
        with contextlib.suppress(Exception):
            container.stop()
        raise

    logger.info("integration database ready at %s", database_url)
    try:
        yield database_url
    finally:
        with contextlib.suppress(Exception):
            container.stop()
