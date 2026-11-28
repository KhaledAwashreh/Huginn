"""Launch the account email preflight with its read-only PostgreSQL query."""

from huginn.management.application.read_models.account_email_candidate import (
    AccountEmailCandidate,
)
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.queries.account_email_preflight import (
    read_account_email_candidates,
)
from huginn.management.presentation.cli import account_email_preflight


def _read_candidates(database_url: str) -> tuple[AccountEmailCandidate, ...]:
    connection = ManagementConnectionFactory(
        database_url, statement_timeout_ms=15000
    ).connect()
    try:
        return read_account_email_candidates(connection)
    finally:
        connection.close()


def main(argv: list[str] | None = None, *, database_url: str | None = None) -> int:
    return account_email_preflight.main(
        argv, candidates_factory=_read_candidates, database_url=database_url
    )


if __name__ == "__main__":
    raise SystemExit(main())
