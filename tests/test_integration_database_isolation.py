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

That test is a text grep, so it cannot distinguish a module that opens a
connection from one that only asserts on the parsed value. `load_config()`
cannot be tested directly without naming both variables, because the database
variable is read first and a test of either branch has to set and assert on both
names. `_ALLOWED_FILES` therefore names the modules permitted to say the string
anyway, and a third test bounds that exemption by asserting the allowlisted
modules name no driver and no container library. The exemption is per-file and
short on purpose: adding a name to `_ALLOWED_FILES` is a decision to review, not
a convenience.
"""

from __future__ import annotations

from pathlib import Path

from tests.postgres_harness import TEST_DATABASE_STAMP, database_stamp

_TESTS_DIR = Path(__file__).resolve().parent

_GUARD_FILES = frozenset(
    {
        "test_integration_database_isolation.py",
        "management/test_database_isolation.py",
    }
)
"""The guard modules themselves, exempt by path.

They have to name the variables in order to say what they forbid, and this
file's own docstring is why: a docstring mention is allowed and is not the
defect, the file is parsed as text rather than as code precisely because the
point is the name appearing. Exempted by path rather than by basename, because
the management guard is a different file that happens to be about the same
subject, and a basename rule would exempt any future `test_database_isolation.py`
in any directory without anyone deciding it.
"""

_ALLOWED_FILES = frozenset(
    {
        "test_config.py",
        "management/test_config.py",
        "management/test_app.py",
        "management/test_main.py",
    }
)
"""Modules permitted to name a database URL variable despite being unable to
connect. Keyed by path relative to tests/, not by basename: two of these share
the name `test_config.py`, and matching on basename silently exempted whichever
one was not meant to be, which is a wider exemption than this docstring claims.

`test_config.py` and `management/test_config.py` exercise their respective
`load_config()`, which reads the database variable before anything else, so any
correct test of either branch has to set and assert on both names. They are pure
unit tests that never hand the value to a driver, which the third test below
enforces.

`management/test_app.py` and `management/test_main.py` name the variable only
inside a RuntimeError message, to assert that a missing configuration fails
before a readiness probe or a server is constructed. They cannot connect either,
and the third test below holds them to that.

Held to these four files: do not widen without deciding the exposure on purpose.
"""

_CONNECTION_SYMBOLS = ("psycopg", "testcontainers", "integration_database_url")
"""Everything that could open or provision a connection *from the ELT suite's
route*. A driver import, the container library, and the fixture are the only
available routes, so naming none of the three is enough to show the file cannot
reach a database.

The management fixtures are deliberately absent. Naming
`management_database_url` appears in two allowlisted files only inside their own
test function names, which would make this check fire on a rename rather than on
a real capability. The management suite's provenance is covered by the stronger
positive check instead: the stamp assertion above it, which asks the database
whether the suite provisioned it."""

_ENVIRONMENT_URL_VARIABLES = ("HUGINN_DATABASE_URL", "HUGINN_MANAGEMENT_DATABASE_URL")
"""Every environment variable that can name a real database. The management
variable contains a schema and a suite of its own, and a test that derived a
connection from it would reach a developer's real management database without
tripping a guard that only knew about the first name."""


def test_the_suite_database_was_provisioned_by_this_suite(
    integration_database_url: str,
):
    """The suite's database must carry the stamp the harness writes on creation.

    A dev database, a CI service database, or anything else the suite did not
    provision itself has no such comment, so this fails against it rather than
    skipping. Deliberately does not read HUGINN_DATABASE_URL: comparing against
    an environment variable is what made the previous version of this guard
    vacuous on CI.

    The management suite's equivalent is
    tests/management/test_database_isolation.py. It cannot live here: a fixture
    defined in tests/management/conftest.py is not in scope from tests/, so this
    module cannot request management_database_url at all.
    """
    stamp = database_stamp(integration_database_url)

    assert stamp == TEST_DATABASE_STAMP, (
        "the database the integration suite is about to use was not provisioned "
        "by the suite: it carries no provisioning stamp, so it is a pre-existing "
        "database and the suite is about to read and rewrite real data. The "
        "suite must only ever use the throwaway Postgres its own fixture starts."
    )


def test_no_test_module_derives_its_connection_from_the_environment():
    """No module under tests/ may name a database URL variable, by any route,
    except the ones `_ALLOWED_FILES` names.

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
        f"{path.relative_to(_TESTS_DIR)} ({variable})"
        for path in _TESTS_DIR.rglob("*.py")
        if str(path.relative_to(_TESTS_DIR)) not in _GUARD_FILES
        and str(path.relative_to(_TESTS_DIR)) not in _ALLOWED_FILES
        for variable in _ENVIRONMENT_URL_VARIABLES
        if variable in path.read_text()
    )

    assert not offenders, (
        "these modules name a database URL variable, so a connection derived "
        "from the environment can reach the suite again, directly or through "
        f"os.getenv, dotenv_values, or a from-import. Take it from a fixture "
        f"instead: {offenders}"
    )


def test_allowlisted_files_still_cannot_reach_a_database():
    """The exemption must stay an exemption.

    The grep above cannot see intent, so it exempts a file on the strength of
    its name appearing in `_ALLOWED_FILES`. This asserts the reason that
    exemption is defensible still holds: an allowlisted module names no driver,
    no container library, and no connection fixture, so it has no route to a
    database even if someone later edits it. Without this, widening
    `_ALLOWED_FILES` would degrade the guard silently.
    """
    offenders = sorted(
        f"{name} names {symbol}"
        for name in _ALLOWED_FILES
        for symbol in _CONNECTION_SYMBOLS
        if symbol in (_TESTS_DIR / name).read_text()
    )

    assert not offenders, (
        "these allowlisted modules name something that can open a database, so "
        "the exemption the static grep grants them is no longer earned. Keep "
        "them connection-free, or move them to a file that takes a database "
        f"fixture: {offenders}"
    )
