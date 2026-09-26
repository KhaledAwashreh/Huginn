"""Provenance check for the management suite's database.

The ELT suite has an equivalent at tests/test_integration_database_isolation.py.
It cannot be shared from there: a fixture defined in tests/management/conftest.py
is not in scope from tests/, so that module cannot request
management_database_url at all.

This exists because the management suite's fixture used to build its own
Postgres container and never write the provisioning stamp, so the guard that
protects the ELT suite from running against a developer's real data had no
counterpart here. A management test pointed at a developer's real management
database would have failed nothing. Both suites now provision through
tests/postgres_harness.py, and this is the check that keeps that true.
"""

from __future__ import annotations

from tests.postgres_harness import TEST_DATABASE_STAMP, database_stamp


def test_the_management_suite_database_was_provisioned_by_this_suite(
    management_database_url: str,
):
    """The management database must carry the stamp the harness writes.

    A database the suite did not provision has no such comment, so this fails
    against it rather than skipping. Deliberately does not read
    HUGINN_MANAGEMENT_DATABASE_URL: comparing against an environment variable
    is what made the ELT guard vacuous on CI, where the variable is unset.
    """
    stamp = database_stamp(management_database_url)

    assert stamp == TEST_DATABASE_STAMP, (
        "the database the management suite is about to use was not provisioned "
        "by the suite: it carries no provisioning stamp, so it is a pre-existing "
        "database and the suite is about to read and rewrite real data. The "
        "suite must only ever use the throwaway Postgres its own fixture starts."
    )
