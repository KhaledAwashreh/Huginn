"""The one place a test Postgres is provisioned.

Two conftests need a throwaway Postgres: tests/conftest.py for the ELT
suite, tests/management/conftest.py for the management suite. They
arrived independently, from two branches, and each built its own container
and applied its own copy of the six base schema files. That is two answers
to "how does a test get a database" and they had already diverged: only one
of them stamped the database, so only one of them could be checked for
provenance.

Both policies are now this one. The stamp matters most: it is what
`tests/test_integration_database_isolation.py` asserts on, and it is the
only evidence that distinguishes a database this suite provisioned from a
developer's own, since CI sets no database variable to compare against.

Two failure modes are distinguished deliberately, and neither is a skip:

1. The container cannot start, or testcontainers is not installed. That is
   the environment, not the code. Failing rather than skipping matters
   because a skip here leaves every real-SQL and every migration test
   silently absent, which reads exactly like those tests passing, so an
   unreachable Docker daemon or a Docker Hub rate limit would produce a
   green build.
2. Applying db/schema/*.sql raises. By then Docker and Postgres have both
   proven themselves working, so the SQL itself is broken. That is a real
   bug and must not be laundered into a quiet skip either.

Schema application failing does not stop the container on its own, hence
the explicit stop in that branch.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

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

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "db" / "schema"

SCHEMA_FILES = (
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

Deliberately excludes the fourteen ALTER files. Applying them would test
the upgrade path rather than the shipped shape, and the two are allowed to
differ; README.md explains why the fresh-install rebuild is not a
substitute for migration coverage.
"""

_POSTGRES_IMAGE = "postgres:16-alpine"

logger = logging.getLogger(__name__)


def _start_container(dbname: str):
    """Return a started Postgres container, or fail the run.

    Fails rather than skips; see this module's docstring for why that
    distinction is load-bearing.
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
            dbname=dbname,
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
        pytest.fail(
            "could not start a Postgres container, so the integration suite "
            f"did not run. Is the Docker daemon reachable? ({exc})"
        )
    return container


def database_stamp(database_url: str) -> str | None:
    """Return the provisioning comment on a database, or None if it has none.

    A fact about the database, not an assertion about it, so both the ELT and
    the management guard can read it without importing each other's tests.
    """
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        return conn.execute(
            "SELECT shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()[0]


@contextlib.contextmanager
def provisioned_postgres(dbname: str, *, apply_schema: bool = True) -> Iterator[str]:
    """Yield a URL to a throwaway Postgres, stamped as suite-provisioned.

    `apply_schema=False` yields a genuinely empty database, for the tests
    that assert what the management readiness probe makes of a database
    that was never bootstrapped. Such a database is still stamped: it is
    suite-provisioned, and the stamp is a statement about provenance, not
    about whether the schema was applied.
    """
    container = _start_container(dbname)
    database_url = container.get_connection_url()
    try:
        with psycopg.connect(database_url, autocommit=True) as conn:
            if apply_schema:
                for filename in SCHEMA_FILES:
                    conn.execute((SCHEMA_DIR / filename).read_text())
            conn.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(dbname), sql.Literal(TEST_DATABASE_STAMP)
                )
            )
    except Exception:
        with contextlib.suppress(Exception):
            container.stop()
        raise

    logger.info("test database %s ready (schema applied: %s)", dbname, apply_schema)
    try:
        yield database_url
    finally:
        with contextlib.suppress(Exception):
            container.stop()
