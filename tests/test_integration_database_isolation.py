"""Regression tripwires for the integration suite's connection target.

The bug these exist for: tests/conftest.py used to short-circuit its
testcontainers path whenever a database named by HUGINN_DATABASE_URL answered
a query, which on any developer machine meant every integration test ran
against real dev data, and the CREATE DATABASE / DROP DATABASE migration tests
created and dropped scratch databases on the real server.

The invariant: the database the suite runs against is one the suite itself
provisioned. Nothing else is acceptable, and the check must not depend on the
environment, because CI does not set HUGINN_DATABASE_URL and a guard that reads
it skips in exactly the place a regression would ship.

So the fixture stamps the database it creates (conftest.TEST_DATABASE_STAMP,
written with COMMENT ON DATABASE) and the first test below asserts the stamp is
there. A database the developer keeps their data in has no such comment, so the
assertion fails against it. That is positive evidence of provenance, available
identically on a laptop and on a runner, with no second database required.

The second test is the static half: no module under tests/ may derive a
connection from the environment at all, directly or indirectly.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from tests.conftest import TEST_DATABASE_STAMP

_TESTS_DIR = Path(__file__).resolve().parent
_THIS_FILE = Path(__file__).name
"""The one place the variable may be named, and it is named to assert nothing
else is. Every other module has to receive its connection by injection."""


def test_the_suite_database_was_provisioned_by_this_suite(
    integration_database_url: str,
):
    """The suite's database must carry the stamp conftest writes on creation.

    A dev database, a CI service database, or anything else the suite did not
    provision itself has no such comment, so this fails against it rather than
    skipping. Deliberately does not read HUGINN_DATABASE_URL: comparing against
    an environment variable is what made the previous version of this guard
    vacuous on CI.
    """
    with psycopg.connect(integration_database_url, connect_timeout=5) as conn:
        stamp = conn.execute(
            "SELECT shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()[0]

    assert stamp == TEST_DATABASE_STAMP, (
        "the database the integration suite is about to use was not provisioned "
        "by the suite: it carries no provisioning stamp, so it is a pre-existing "
        "database and the suite is about to read and rewrite real data. The "
        "suite must only ever use the throwaway Postgres its own fixture starts."
    )


def test_no_test_module_derives_its_connection_from_the_environment():
    """No module under tests/ may name HUGINN_DATABASE_URL, by any route.

    Naming the variable at all is the defect, not the particular way it is
    read, so this matches the bare string rather than a set of call patterns. An
    earlier version matched `os.environ.get(` and `os.environ[`, which an
    earlier version of this guard was supposed to catch and did not:
    `os.getenv(...)`, `from os import environ` followed by `environ[...]`,
    `from os import getenv`, and `dotenv_values()[...]` all slipped past it.

    Every route to the value has to name it somewhere, so matching the string
    closes the class rather than the instances. A docstring mention is allowed
    and is not the defect; the file is parsed as text, not as code, because the
    point is the name appearing, not which expression consumes it.
    """
    offenders = sorted(
        str(path.relative_to(_TESTS_DIR))
        for path in _TESTS_DIR.rglob("*.py")
        if path.name != _THIS_FILE and "HUGINN_DATABASE_URL" in path.read_text()
    )

    assert not offenders, (
        "these modules name HUGINN_DATABASE_URL, so a connection derived from "
        "the environment can reach the suite again, directly or through "
        f"os.getenv, dotenv_values, or a from-import. Take it from the "
        f"integration_database_url fixture instead: {offenders}"
    )
