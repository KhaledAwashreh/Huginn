"""Read the source identity rows for the email cutover audit."""

from huginn.management.application.read_models.account_email_candidate import (
    AccountEmailCandidate,
)
from huginn.management.persistence.contracts.database import DatabaseSession


def read_account_email_candidates(
    connection: DatabaseSession,
) -> tuple[AccountEmailCandidate, ...]:
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            "SELECT a.id, u.id IS NOT NULL, r.verification_required, "
            "u.email, r.pending_email, r.verified_email "
            "FROM operational.accounts a "
            "LEFT JOIN operational.users u ON u.account_id = a.id "
            "LEFT JOIN operational.account_recovery_identity r ON r.account_id = a.id "
            "ORDER BY a.id"
        )
        return tuple(AccountEmailCandidate(*row) for row in cursor.fetchall())
