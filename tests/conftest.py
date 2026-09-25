"""Shared pytest fixtures for the whole suite. See CLAUDE.md code standard
4 and Jira KAN-52.

The integration database is provisioned here, never discovered. A suite that
falls back to whatever the developer's environment happens to name re-runs the
whole pipeline over real dev rows and creates scratch databases on the
developer's own server, so the only URL an integration test ever sees is the one
the fixture below starts.
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

TEST_DATABASE_STAMP = "huginn-testcontainer"
"""Written to the provisioned database's own COMMENT, and asserted by
tests/test_integration_database_isolation.py.

The stamp is what makes the isolation guard work without depending on any
environment variable. The guard's question is "is the suite about to run
against a database the developer cares about?", and the only way to answer
that without trusting the environment is to ask the database itself: a
database this suite provisioned carries this comment, and nothing else does.
Comparing against the developer's own connection setting instead would make the
guard skip exactly where it matters most, since CI does not set that variable
and so has no developer database to compare against.
"""

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

    Fails rather than skips when testcontainers or Docker is unavailable.
    Because the fixture is session-scoped and only integration tests request
    it, that failure is confined to them: the DB-free unit tests still run and
    still pass, and the run as a whole exits non-zero. Skipping was the wrong
    answer for a suite whose integration tests are the point, since an
    unreachable daemon, a Docker Hub rate limit, or a failed image pull would
    otherwise produce a green build with every real-SQL and every migration
    test silently absent, which reads exactly like those tests passing.

    The weaker failure this also guards against is a suite that quietly falls
    back to a reachable database and runs against whatever the developer keeps
    in it. Nothing here reads the environment to choose a target; the
    provisioned database is stamped with TEST_DATABASE_STAMP and
    tests/test_integration_database_isolation.py asserts the stamp is present.
    """
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError as exc:
        pytest.fail(
            "testcontainers is not installed, so the integration suite cannot "
            f"run. Install the dev group with `uv sync`. ({exc})"
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
        #
        # This fails the run rather than skipping it. Skipping is the wrong
        # answer for a suite whose integration tests are the point: an
        # unavailable Docker daemon, a Docker Hub rate limit, or a failed image
        # pull would otherwise yield a green build with every real-SQL and
        # every migration test silently absent, which is indistinguishable
        # from those tests passing.
        if container is not None:
            with contextlib.suppress(Exception):
                container.stop()
        pytest.fail(
            "could not start a Postgres container, so the integration suite "
            f"did not run. Is the Docker daemon reachable? ({exc})"
        )

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
            conn.execute(f"COMMENT ON DATABASE huginn IS '{TEST_DATABASE_STAMP}'")
    except Exception:
        with contextlib.suppress(Exception):
            container.stop()
        raise

    logger.info("integration database ready")
    try:
        yield database_url
    finally:
        with contextlib.suppress(Exception):
            container.stop()
