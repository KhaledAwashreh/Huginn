"""Shared pytest fixtures for the whole suite. See CLAUDE.md code standard
4 and Jira KAN-52.

The integration database is provisioned here, never discovered. A suite that
falls back to whatever the developer's environment happens to name re-runs the
whole pipeline over real dev rows and creates scratch databases on the
developer's own server, so the only URL an integration test ever sees is the one
the fixture below starts.

How that database gets built is not decided here. `tests/postgres_harness.py`
owns it, because the management suite needs an identically provisioned
Postgres and two independent answers to this question had already diverged:
only this one stamped the database, so only this one could be checked for
provenance. The fixture here is the ELT suite's use of that shared policy.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from dotenv import load_dotenv

from tests.postgres_harness import TEST_DATABASE_STAMP, provisioned_postgres

load_dotenv()
"""Nothing here connects through the developer's URL, so the only reason to
read .env is tests/test_integration_database_isolation.py, which needs the
value to prove the suite is pointed somewhere else. Removing this would
silently disarm that tripwire.
"""

logger = logging.getLogger(__name__)

__all__ = ["TEST_DATABASE_STAMP", "integration_database_url"]


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
    with provisioned_postgres("huginn") as database_url:
        yield database_url
