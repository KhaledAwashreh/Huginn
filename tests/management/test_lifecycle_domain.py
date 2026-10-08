from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.management.domain.entities.account_lifecycle_proof import (
    AccountLifecycleProof,
)
from huginn.management.domain.entities.account_recovery_identity import (
    AccountRecoveryIdentity,
)
from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.domain.value_objects.verification_state import (
    VerificationState,
)


def test_recovery_identity_derives_pending_verified_and_trusted_states():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    trusted = AccountRecoveryIdentity(uuid4(), False, None, None, None, now, now)
    pending = replace(trusted, pending_email="ada@example.test")
    verified = replace(
        pending,
        pending_email=None,
        verified_email="ada@example.test",
        verified_at=now,
    )

    assert trusted.verification_state is VerificationState.TRUSTED
    assert pending.verification_state is VerificationState.PENDING
    assert verified.verification_state is VerificationState.VERIFIED


def test_recovery_identity_rejects_conflicting_verification_addresses():
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(LifecycleProofError, match="pending_email"):
        AccountRecoveryIdentity(
            uuid4(),
            True,
            "ada@example.test",
            "old@example.test",
            now,
            now,
            now,
        )


def test_recovery_identity_rejects_naive_or_reversed_timestamps():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(LifecycleProofError, match="created_at"):
        AccountRecoveryIdentity(
            uuid4(), False, None, None, None, now.replace(tzinfo=None), now
        )

    with pytest.raises(LifecycleProofError, match="updated_at"):
        AccountRecoveryIdentity(
            uuid4(), False, None, None, None, now, now - timedelta(seconds=1)
        )


def test_lifecycle_proof_requires_expiry_after_creation_and_aware_times():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = (
        uuid4(),
        uuid4(),
        "a" * 64,
        ProofPurpose.VERIFY_EMAIL,
        "ada@example.test",
    )

    with pytest.raises(LifecycleProofError, match="expires_at"):
        AccountLifecycleProof(*values, now, None, False, now)

    with pytest.raises(LifecycleProofError, match="created_at"):
        AccountLifecycleProof(
            *values,
            now + timedelta(hours=1),
            None,
            False,
            now.replace(tzinfo=None),
        )


def test_lifecycle_proof_purposes_are_explicit_and_secrets_are_redacted():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    proof = AccountLifecycleProof(
        uuid4(),
        uuid4(),
        "b" * 64,
        ProofPurpose.RESET_PASSWORD,
        "private@example.test",
        now + timedelta(minutes=30),
        None,
        False,
        now,
    )

    assert [purpose.value for purpose in ProofPurpose] == [
        "verify_email",
        "reset_password",
    ]
    assert "b" * 64 not in repr(proof)
    assert "private@example.test" not in repr(proof)
    with pytest.raises(FrozenInstanceError):
        proof.superseded = True


@pytest.mark.parametrize(
    "digest", ["not-a-sha256-digest", "a" * 63, "A" * 64, "g" * 64]
)
def test_lifecycle_proof_rejects_non_sha256_token_digests(digest):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(LifecycleProofError, match="token_digest"):
        AccountLifecycleProof(
            uuid4(),
            uuid4(),
            digest,
            ProofPurpose.VERIFY_EMAIL,
            "ada@example.test",
            now + timedelta(hours=1),
            None,
            False,
            now,
        )


@pytest.mark.parametrize(
    ("account_id", "verification_required", "field_name"),
    [("not-a-uuid", False, "account_id"), (uuid4(), 1, "verification_required")],
)
def test_recovery_identity_rejects_invalid_uuid_and_boolean_types(
    account_id, verification_required, field_name
):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(LifecycleProofError, match=field_name):
        AccountRecoveryIdentity(
            account_id,
            verification_required,
            None,
            None,
            None,
            now,
            now,
        )


@pytest.mark.parametrize(
    ("id", "account_id", "superseded", "field_name"),
    [
        ("not-a-uuid", uuid4(), False, "id"),
        (uuid4(), "not-a-uuid", False, "account_id"),
        (uuid4(), uuid4(), 0, "superseded"),
    ],
)
def test_lifecycle_proof_rejects_invalid_uuid_and_boolean_types(
    id, account_id, superseded, field_name
):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(LifecycleProofError, match=field_name):
        AccountLifecycleProof(
            id,
            account_id,
            "c" * 64,
            ProofPurpose.VERIFY_EMAIL,
            "ada@example.test",
            now + timedelta(hours=1),
            None,
            superseded,
            now,
        )


def test_recovery_identity_hides_addresses_from_repr():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    identity = AccountRecoveryIdentity(
        uuid4(), True, "private@example.test", None, None, now, now
    )

    assert "private@example.test" not in repr(identity)
