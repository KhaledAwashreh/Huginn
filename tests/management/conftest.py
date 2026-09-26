"""Database fixtures for the management suite.

The provisioning itself is `tests/postgres_harness.provisioned_postgres`, the
same policy tests/conftest.py uses for the ELT suite. This file existed
separately and rebuilt the container and the schema-file list inline, which
meant the two suites had two answers to "how does a test get a database" and
only one of them stamped what it created, so only one could be checked for
provenance. See tests/postgres_harness.py.

Two databases, because two different starting states are needed:

1. `management_database_url` has the schema applied, for the tests that
   exercise real operational tables.
2. `empty_management_database_url` has none, for the tests that assert what
   the readiness probe makes of a database that was never bootstrapped.

The second stays function-scoped. It is not merely unused, it must be unused,
so making it session-scoped to save container starts would let the first test
that creates a table decide what every later test sees, and
test_ready_detects_missing_required_column would stop meaning anything.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.postgres_harness import provisioned_postgres


@pytest.fixture(scope="session")
def management_database_url() -> Iterator[str]:
    with provisioned_postgres("huginn_management_test") as database_url:
        yield database_url


@pytest.fixture
def empty_management_database_url() -> Iterator[str]:
    with provisioned_postgres(
        "huginn_management_empty_test", apply_schema=False
    ) as database_url:
        yield database_url
