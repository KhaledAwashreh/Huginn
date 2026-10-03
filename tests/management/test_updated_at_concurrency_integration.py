from uuid import uuid4

import psycopg

from huginn.management.domain.account import NewAccount
from huginn.management.repositories.postgres.account import PostgresAccountRepository


def test_earlier_transaction_writing_last_gets_later_updated_at(
    management_database_url,
):
    username = f"updated-at-race-{uuid4()}"
    with psycopg.connect(management_database_url) as setup_connection:
        account = PostgresAccountRepository(setup_connection).create(
            NewAccount(username, "placeholder")
        )

    try:
        with (
            psycopg.connect(management_database_url) as earlier,
            psycopg.connect(management_database_url) as later,
        ):
            transaction_started_at = earlier.execute(
                "SELECT transaction_timestamp()"
            ).fetchone()[0]

            later_update = PostgresAccountRepository(later).set_status(
                account.id, "disabled"
            )
            later.commit()

            # Keep the earlier transaction open long enough that a
            # transaction-start timestamp is unambiguously stale.
            earlier.execute("SELECT pg_sleep(0.02)")
            earlier_update = PostgresAccountRepository(earlier).set_status(
                account.id, "active"
            )
            earlier.commit()

            assert later_update is not None
            assert earlier_update is not None
            assert transaction_started_at < later_update.updated_at
            assert earlier_update.updated_at > later_update.updated_at
    finally:
        with psycopg.connect(management_database_url) as cleanup_connection:
            cleanup_connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account.id,)
            )
