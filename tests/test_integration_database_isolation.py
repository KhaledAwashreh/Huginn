"""Regression tripwire for the integration suite's connection target.

The bug this exists for: tests/conftest.py used to short-circuit the
testcontainers path whenever a database named by HUGINN_DATABASE_URL
answered a query, which on any developer machine meant every integration
test ran against real dev data, and the CREATE DATABASE / DROP DATABASE
migration tests created and dropped scratch databases on the real server.

The invariant, stated once so both regressions are caught: whatever the
suite connects to must not be the database the developer's own
environment points at, and the suite must reach that target by injection
rather than by writing os.environ["HUGINN_DATABASE_URL"] for its callers
to read back. Comparing against the live server rather than the DSN
string catches the second case too, because a suite that overwrites the
variable makes the two look identical.
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path

import psycopg
import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_THIS_FILE = Path(__file__).name
"""The one place the developer's URL may be read is here, where it is read
to be compared against. Every other module has to receive its connection by
injection.
"""
_DEVELOPER_URL_READ = re.compile(
    r"""os\.environ(?:\.get\(|\[)\s*["']HUGINN_DATABASE_URL"""
)


def _database_identity(database_url: str) -> tuple[str | None, str | None, str, str]:
    """Return enough of a server's identity to tell two databases apart.

    Two URLs naming the same database must agree on all four parts. The
    system identifier alone is authoritative for "same cluster", but
    pg_control_system() is superuser-only, so the network coordinates
    stand in for it when it cannot be read; a testcontainers instance and
    a developer's local server never share those either.
    """
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        system_identifier = None
        with contextlib.suppress(psycopg.Error):
            system_identifier = conn.execute(
                "SELECT system_identifier::text FROM pg_control_system()"
            ).fetchone()[0]
        address, port, database = conn.execute(
            "SELECT inet_server_addr()::text, inet_server_port(), current_database()"
        ).fetchone()
    return system_identifier, address, str(port), database


def test_integration_database_is_not_the_developers_own_database(
    integration_database_url: str,
):
    """The suite's database must not be the one HUGINN_DATABASE_URL names."""
    developer_url = os.environ.get("HUGINN_DATABASE_URL")
    if developer_url is None:
        pytest.skip("HUGINN_DATABASE_URL is unset, so there is no developer database")

    try:
        developer_identity = _database_identity(developer_url)
    except psycopg.Error:
        # The URL is not echoed into the skip reason: it carries a password,
        # and pytest prints skip reasons in the summary.
        pytest.skip(
            "HUGINN_DATABASE_URL is unreachable, so there is no developer "
            "database to compare against"
        )

    suite_identity = _database_identity(integration_database_url)

    assert suite_identity != developer_identity, (
        "the integration suite is about to run against the same database as "
        "HUGINN_DATABASE_URL, so it would read and rewrite real dev data; "
        "the suite must use a database it provisioned itself"
    )


def test_no_test_module_derives_its_connection_from_the_developers_url():
    """No module under tests/ may read HUGINN_DATABASE_URL out of the environment.

    Reading it is how the suite ends up pointed at whatever the developer's
    shell happens to say, with the whole pipeline re-running over real rows.
    Injection is the fix, so the absence of the read is the invariant worth
    asserting. The pattern matches the read itself rather than a bare
    mention, so a docstring or a commit-style citation stays allowed.
    """
    offenders = sorted(
        str(path.relative_to(_TESTS_DIR))
        for path in _TESTS_DIR.rglob("*.py")
        if path.name != _THIS_FILE and _DEVELOPER_URL_READ.search(path.read_text())
    )

    assert not offenders, (
        "these modules read HUGINN_DATABASE_URL instead of taking the "
        f"connection from the integration_database_url fixture: {offenders}"
    )
