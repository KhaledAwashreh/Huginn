from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from huginn.management.application.errors.lifecycle import (
    LifecycleConflictError,
    LifecycleIntegrityError,
    LifecycleRateLimitError,
)
from huginn.management.application.read_models.account_security import AccountSecurity
from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)
from huginn.management.application.read_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRecord,
)
from huginn.management.application.read_models.lifecycle_throttle import (
    LifecycleThrottleReservation,
)
from huginn.management.application.read_models.mail_delivery_claim import (
    MailDeliveryClaim,
)
from huginn.management.persistence.row_models.account_lifecycle_proof import (
    AccountLifecycleProofRow,
)
from huginn.management.persistence.row_models.account_recovery_identity import (
    AccountRecoveryIdentityRow,
)
from huginn.management.persistence.row_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRow,
)
from huginn.management.persistence.row_models.lifecycle_throttle import (
    LifecycleThrottleRow,
)


def test_account_security_projection_hides_recovery_email_and_is_frozen():
    security = AccountSecurity(
        username="ada",
        email_verification_required=True,
        email_verified=False,
        recovery_email="private@example.test",
    )

    assert "private@example.test" not in repr(security)
    with pytest.raises(FrozenInstanceError):
        security.email_verified = True


def test_lifecycle_mail_message_hides_recipient_and_proof_from_repr():
    message = LifecycleMailMessage(
        recipient="private@example.test",
        purpose="verify_email",
        token="secret-proof",
    )

    assert "private@example.test" not in repr(message)
    assert "secret-proof" not in repr(message)


def test_lifecycle_mail_outbox_projection_hides_encrypted_payload():
    record = LifecycleMailOutboxRecord(
        id=uuid4(),
        account_id=uuid4(),
        proof_id=uuid4(),
        purpose="reset_password",
        encrypted_payload=b"opaque-secret-payload",
        next_attempt_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert "opaque-secret-payload" not in repr(record)
    with pytest.raises(FrozenInstanceError):
        record.next_attempt_at = datetime(2026, 1, 2, tzinfo=UTC)


def test_lifecycle_throttle_reservation_is_an_immutable_admission_result():
    reservation = LifecycleThrottleReservation(
        allowed=False,
        retry_after_seconds=60,
    )

    assert (reservation.allowed, reservation.retry_after_seconds) == (False, 60)
    with pytest.raises(FrozenInstanceError):
        reservation.allowed = True


def test_mail_delivery_claim_hides_claim_token_and_payload():
    claim = MailDeliveryClaim(
        id=uuid4(),
        account_id=uuid4(),
        proof_id=uuid4(),
        purpose="verify_email",
        encrypted_payload=b"encrypted-proof",
        claim_token=uuid4(),
        attempt_count=2,
        lease_until=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert "encrypted-proof" not in repr(claim)
    assert str(claim.claim_token) not in repr(claim)


def test_identity_row_rejects_unknown_persisted_fields():
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(ValidationError):
        AccountRecoveryIdentityRow(
            account_id=uuid4(),
            verification_required=True,
            pending_email="private@example.test",
            verified_email=None,
            verified_at=None,
            created_at=now,
            updated_at=now,
            unexpected="ignored fields must fail",
        )


def test_proof_row_accepts_only_lifecycle_purposes_and_has_no_updated_at():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = {
        "id": uuid4(),
        "account_id": uuid4(),
        "token_digest": "digest-value",
        "purpose": "verify_email",
        "destination": "private@example.test",
        "expires_at": datetime(2026, 1, 2, tzinfo=UTC),
        "consumed_at": None,
        "superseded": False,
        "created_at": now,
    }

    row = AccountLifecycleProofRow(**values)

    assert row.purpose == "verify_email"
    assert "digest-value" not in repr(row)
    assert "private@example.test" not in repr(row)
    with pytest.raises(ValidationError):
        AccountLifecycleProofRow(**{**values, "purpose": "other"})
    with pytest.raises(ValidationError):
        AccountLifecycleProofRow(**{**values, "updated_at": now})


def test_outbox_row_rejects_unknown_delivery_state():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = {
        "id": uuid4(),
        "account_id": uuid4(),
        "purpose": "reset_password",
        "proof_id": uuid4(),
        "encrypted_payload": b"ciphertext",
        "attempt_count": 0,
        "next_attempt_at": now,
        "state": "pending",
        "failure_code": None,
        "claim_token": None,
        "claimed_at": None,
        "lease_until": None,
        "created_at": now,
        "updated_at": now,
        "sent_at": None,
    }

    row = LifecycleMailOutboxRow(**values)
    assert row.state == "pending"
    assert "ciphertext" not in repr(row)
    with pytest.raises(ValidationError):
        LifecycleMailOutboxRow(**{**values, "state": "delivered"})


def test_throttle_row_rejects_unknown_scope_and_is_frozen():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = {
        "scope": "receipt_username",
        "key_digest": "digest-value",
        "window_started_at": now,
        "request_count": 1,
        "created_at": now,
        "updated_at": now,
    }

    row = LifecycleThrottleRow(**values)

    assert "digest-value" not in repr(row)
    with pytest.raises(ValidationError):
        LifecycleThrottleRow(**{**values, "scope": "username"})
    with pytest.raises(ValidationError):
        row.request_count = 2


def test_lifecycle_rate_limit_error_exposes_retry_delay():
    error = LifecycleRateLimitError("lifecycle requests are temporarily limited", 45)

    assert error.retry_after_seconds == 45
    assert str(error) == "lifecycle requests are temporarily limited"
    from huginn.management.application.errors.errors import RateLimitError
    from huginn.management.domain.errors.errors import (
        ConflictError,
        ManagementDomainError,
    )

    assert issubclass(LifecycleRateLimitError, RateLimitError)
    assert issubclass(LifecycleConflictError, ConflictError)
    assert issubclass(LifecycleIntegrityError, ManagementDomainError)
