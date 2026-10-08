from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import ValidationError

from huginn.management.domain.entities.account_lifecycle_proof import (
    AccountLifecycleProof,
)
from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.account_lifecycle_proof import (
    PostgresAccountLifecycleProofRepository,
)
from huginn.management.persistence.repositories.account_recovery_identity import (
    PostgresAccountRecoveryIdentityRepository,
)


def _create_account(connection: psycopg.Connection) -> UUID:
    account = PostgresAccountRepository(PsycopgDatabaseSession(connection)).create(
        NewAccount(f"Lifecycle-{uuid4()}", "test-hash")
    )
    return account.id


def test_live_recovery_identity_repository_enrolls_and_verifies(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        connection.execute("SAVEPOINT lifecycle_identity_repository")
        try:
            account_id = _create_account(connection)
            repository = PostgresAccountRecoveryIdentityRepository(
                PsycopgDatabaseSession(connection)
            )
            pending = repository.create(
                account_id,
                verification_required=True,
                pending_email="ada@example.test",
            )

            assert repository.get_by_account_id(account_id) == pending
            assert pending.pending_email == "ada@example.test"
            assert pending.verified_email is None

            now = datetime.now(UTC)
            assert (
                repository.verify_email(account_id, "other@example.test", now) is None
            )
            verified = repository.verify_email(account_id, "ada@example.test", now)

            assert verified is not None
            assert verified.pending_email is None
            assert verified.verified_email == "ada@example.test"
            assert verified.verified_at is not None
            assert repository.verify_email(account_id, "ada@example.test", now) is None
            assert repository.set_pending_email(account_id, "new@example.test") is None

            trusted_account_id = _create_account(connection)
            trusted = repository.create(trusted_account_id, verification_required=False)
            assert trusted.pending_email is None
            enrolled = repository.set_pending_email(
                trusted_account_id, "legacy@example.test"
            )
            assert enrolled is not None
            assert enrolled.verification_required is False
            assert enrolled.pending_email == "legacy@example.test"
            enrolled_verified = repository.verify_email(
                trusted_account_id, "legacy@example.test", now
            )
            assert enrolled_verified is not None
            assert enrolled_verified.verified_email == "legacy@example.test"
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT lifecycle_identity_repository")
            connection.execute("RELEASE SAVEPOINT lifecycle_identity_repository")


def test_live_proof_repository_replaces_by_purpose_and_consumes_once(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        connection.execute("SAVEPOINT lifecycle_proof_repository")
        try:
            account_id = _create_account(connection)
            repository = PostgresAccountLifecycleProofRepository(
                PsycopgDatabaseSession(connection)
            )
            now = datetime.now(UTC)
            first = AccountLifecycleProof(
                uuid4(),
                account_id,
                "a" * 64,
                ProofPurpose.VERIFY_EMAIL,
                "first@example.test",
                now + timedelta(hours=1),
                None,
                False,
                now,
            )
            stored_first = repository.replace(first)

            reset = AccountLifecycleProof(
                uuid4(),
                account_id,
                "b" * 64,
                ProofPurpose.RESET_PASSWORD,
                "recovery@example.test",
                now + timedelta(minutes=30),
                None,
                False,
                now,
            )
            stored_reset = repository.replace(reset)

            replacement = AccountLifecycleProof(
                uuid4(),
                account_id,
                "c" * 64,
                ProofPurpose.VERIFY_EMAIL,
                "second@example.test",
                now + timedelta(hours=1),
                None,
                False,
                now,
            )
            stored_replacement = repository.replace(replacement)

            assert repository.get_by_digest("a" * 64).superseded
            assert repository.get_by_id(stored_replacement.id) == stored_replacement
            assert repository.get_by_digest("b" * 64) == stored_reset
            assert repository.get_by_digest("c" * 64) == stored_replacement
            assert repository.consume(stored_replacement.id, now)
            assert not repository.consume(stored_replacement.id, now)
            assert not repository.consume(stored_first.id, now)

            repository.supersede_for_account(account_id, ProofPurpose.RESET_PASSWORD)
            assert repository.get_by_id(stored_reset.id).superseded
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT lifecycle_proof_repository")
            connection.execute("RELEASE SAVEPOINT lifecycle_proof_repository")


def test_live_proof_consume_uses_database_clock_for_expired_proofs(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        connection.execute("SAVEPOINT lifecycle_expired_proof")
        try:
            account_id = _create_account(connection)
            repository = PostgresAccountLifecycleProofRepository(
                PsycopgDatabaseSession(connection)
            )
            actual_now = datetime.now(UTC)
            created_at = actual_now - timedelta(minutes=2)
            expired = repository.replace(
                AccountLifecycleProof(
                    uuid4(),
                    account_id,
                    "d" * 64,
                    ProofPurpose.RESET_PASSWORD,
                    "ada@example.test",
                    actual_now - timedelta(seconds=1),
                    None,
                    False,
                    created_at,
                )
            )

            assert not repository.consume(expired.id, actual_now - timedelta(hours=1))
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT lifecycle_expired_proof")
            connection.execute("RELEASE SAVEPOINT lifecycle_expired_proof")


def test_lifecycle_repository_mappers_reject_invalid_persisted_rows():
    now = datetime.now(UTC)
    identity_row = (
        uuid4(),
        False,
        None,
        None,
        None,
        now,
        now,
    )
    proof_row = (
        uuid4(),
        uuid4(),
        "a" * 64,
        "not-a-purpose",
        "ada@example.test",
        now + timedelta(hours=1),
        None,
        False,
        now,
    )

    with pytest.raises(ValidationError):
        PostgresAccountRecoveryIdentityRepository._map(
            (*identity_row[:1], "false", *identity_row[2:])
        )
    with pytest.raises(ValidationError):
        PostgresAccountLifecycleProofRepository._map(proof_row)


def test_lifecycle_proof_mapper_rejects_invalid_digest_from_storage():
    now = datetime.now(UTC)
    row = (
        uuid4(),
        uuid4(),
        "A" * 64,
        ProofPurpose.VERIFY_EMAIL.value,
        "ada@example.test",
        now + timedelta(hours=1),
        None,
        False,
        now,
    )

    with pytest.raises(LifecycleProofError, match="token_digest"):
        PostgresAccountLifecycleProofRepository._map(row)
