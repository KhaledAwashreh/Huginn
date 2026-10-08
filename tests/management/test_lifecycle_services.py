from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.errors.errors import AuthorizationError
from huginn.management.application.errors.lifecycle import (
    LifecycleConflictError,
    LifecycleRateLimitError,
)
from huginn.management.application.requests.enroll_recovery_email_request import (
    EnrollRecoveryEmailRequest,
)
from huginn.management.application.requests.forgot_password_request import (
    ForgotPasswordRequest,
)
from huginn.management.application.requests.get_account_security_request import (
    GetAccountSecurityRequest,
)
from huginn.management.application.requests.resend_verification_request import (
    ResendVerificationRequest,
)
from huginn.management.application.requests.reset_password_request import (
    ResetPasswordRequest,
)
from huginn.management.application.requests.verify_email_request import (
    VerifyEmailRequest,
)
from huginn.management.application.services.enroll_recovery_email_service import (
    EnrollRecoveryEmailService,
)
from huginn.management.application.services.forgot_password_service import (
    ForgotPasswordService,
)
from huginn.management.application.services.get_account_security_service import (
    GetAccountSecurityService,
)
from huginn.management.application.services.resend_verification_service import (
    ResendVerificationService,
)
from huginn.management.application.services.reset_password_service import (
    ResetPasswordService,
)
from huginn.management.application.services.signup_service import SignupService
from huginn.management.application.services.verify_email_service import (
    VerifyEmailService,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.common import Principal
from tests.lifecycle_service_helpers import account, queued, services, signup_request
from tests.postgres_harness import provisioned_postgres


@pytest.fixture(scope="module")
def lifecycle_database_url():
    with provisioned_postgres("huginn_lifecycle_services") as url:
        yield url


def _signup(url, **overrides):
    build, cipher = services(url, **overrides)
    request = signup_request()
    build(SignupService).execute(request)
    account_id, user_id = account(url, request.username)
    return build, cipher, request, account_id, user_id


def _verify(build, cipher, url, account_id):
    message = queued(url, cipher, account_id, "verify_email")
    build(VerifyEmailService).execute(VerifyEmailRequest(message.token, str(uuid4())))
    return message


def test_signup_atomic_identity_proof_encrypted_intent_and_duplicate_work(
    lifecycle_database_url,
):
    url = lifecycle_database_url
    calls = []
    build, cipher, request, account_id, _ = _signup(
        url, hash_password_fn=lambda p: calls.append(p) or "hash"
    )
    receipt = build(SignupService).execute(
        replace(request, username=request.username.upper())
    )
    assert receipt.message == "Check your email for next steps"
    assert len(calls) == 2
    with psycopg.connect(url) as conn:
        assert conn.execute(
            "SELECT verification_required,pending_email,verified_email FROM operational.account_recovery_identity WHERE account_id=%s",
            (account_id,),
        ).fetchone() == (True, request.email, None)
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.professional_profiles p JOIN operational.users u ON u.id=p.user_id WHERE u.account_id=%s",
                (account_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.account_lifecycle_proofs WHERE account_id=%s",
                (account_id,),
            ).fetchone()[0]
            == 1
        )
    assert queued(url, cipher, account_id, "verify_email").recipient == request.email


def test_signup_validation_and_cipher_failure_leave_no_partial_identity(
    lifecycle_database_url,
):
    url = lifecycle_database_url

    class BrokenCipher:
        def encrypt(self, message):
            raise RuntimeError("encryption unavailable")

    build, _ = services(url, cipher=BrokenCipher())
    request = signup_request()
    with pytest.raises(ValidationDomainError):
        build(SignupService).execute(replace(request, email="invalid"))
    with pytest.raises(RuntimeError, match="encryption unavailable"):
        build(SignupService).execute(request)
    assert account(url, request.username) is None
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.lifecycle_throttle WHERE scope IN (\x27receipt_ip\x27,\x27receipt_username\x27)"
            ).fetchone()[0]
            > 0
        )


def test_concurrent_verification_consumes_once_and_disabled_never_reactivates(
    lifecycle_database_url,
):
    url = lifecycle_database_url
    build, cipher, _, account_id, _ = _signup(url)
    message = queued(url, cipher, account_id, "verify_email")

    def consume(_):
        try:
            build(VerifyEmailService).execute(
                VerifyEmailRequest(message.token, str(uuid4()))
            )
            return True
        except LifecycleProofError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume, range(2))) == [False, True]
    build, cipher, _, disabled_id, _ = _signup(url)
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.accounts SET status=\x27disabled\x27 WHERE id=%s",
            (disabled_id,),
        )
    message = queued(url, cipher, disabled_id, "verify_email")
    with pytest.raises(LifecycleProofError):
        build(VerifyEmailService).execute(
            VerifyEmailRequest(message.token, str(uuid4()))
        )
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT status FROM operational.accounts WHERE id=%s", (disabled_id,)
            ).fetchone()[0]
            == "disabled"
        )
        assert (
            conn.execute(
                "SELECT verified_email FROM operational.account_recovery_identity WHERE account_id=%s",
                (disabled_id,),
            ).fetchone()[0]
            is None
        )


def test_expired_wrong_purpose_and_destination_proofs_fail(lifecycle_database_url):
    url = lifecycle_database_url
    build, cipher, _, account_id, _ = _signup(url)
    message = queued(url, cipher, account_id, "verify_email")
    with pytest.raises(LifecycleProofError):
        build(ResetPasswordService).execute(
            ResetPasswordRequest(message.token, "ResetNow!12345", str(uuid4()))
        )
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.account_recovery_identity SET pending_email=\x27different@example.test\x27 WHERE account_id=%s",
            (account_id,),
        )
    with pytest.raises(LifecycleProofError):
        build(VerifyEmailService).execute(
            VerifyEmailRequest(message.token, str(uuid4()))
        )
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.account_recovery_identity SET pending_email=\x27original@example.test\x27 WHERE account_id=%s",
            (account_id,),
        )
        conn.execute(
            "UPDATE operational.account_lifecycle_proofs SET created_at=%s, expires_at=%s WHERE account_id=%s",
            (
                datetime.now(UTC) - timedelta(hours=2),
                datetime.now(UTC) - timedelta(hours=1),
                account_id,
            ),
        )
    with pytest.raises(LifecycleProofError):
        build(VerifyEmailService).execute(
            VerifyEmailRequest(message.token, str(uuid4()))
        )


def test_resend_cooldown_generic_receipts_and_persisted_limits(lifecycle_database_url):
    url = lifecycle_database_url
    build, _, request, account_id, _ = _signup(url)
    receipt = build(ResendVerificationService).execute(
        ResendVerificationRequest(request.email, request.client_ip)
    )
    unknown = build(ResendVerificationService).execute(
        ResendVerificationRequest(f"{uuid4()}@example.test", str(uuid4()))
    )
    assert receipt == unknown
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.lifecycle_mail_outbox WHERE account_id=%s",
                (account_id,),
            ).fetchone()[0]
            == 1
        )
    for _ in range(3):
        build(ResendVerificationService).execute(
            ResendVerificationRequest(request.email, request.client_ip)
        )
    for _ in range(2):
        with pytest.raises(LifecycleRateLimitError) as error:
            build(ResendVerificationService).execute(
                ResendVerificationRequest(request.email, request.client_ip)
            )
        assert 1 <= error.value.retry_after_seconds <= 3600
    with psycopg.connect(url) as conn:
        from hashlib import sha256

        for scope, key in [
            ("receipt_email", request.email.lower()),
            ("receipt_ip", request.client_ip),
        ]:
            assert (
                conn.execute(
                    "SELECT request_count FROM operational.lifecycle_throttle WHERE scope=%s AND key_digest=%s",
                    (scope, sha256(key.encode()).hexdigest()),
                ).fetchone()[0]
                == 7
            )


def test_reset_concurrent_atomic_revocation_and_contact_separate(
    lifecycle_database_url,
):
    url = lifecycle_database_url
    build, cipher, request, account_id, user_id = _signup(url)
    _verify(build, cipher, url, account_id)
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.users SET email=\x27contact@example.test\x27 WHERE id=%s",
            (user_id,),
        )
        for _ in range(2):
            conn.execute(
                "INSERT INTO operational.sessions (account_id,token_digest,csrf_digest,expires_at) VALUES (%s,%s,%s,%s)",
                (
                    account_id,
                    uuid4().hex * 2,
                    uuid4().hex * 2,
                    datetime.now(UTC) + timedelta(hours=1),
                ),
            )
    build(ForgotPasswordService).execute(
        ForgotPasswordRequest(request.email, str(uuid4()))
    )
    message = queued(url, cipher, account_id, "reset_password")
    assert message.recipient == request.email
    with psycopg.connect(url) as conn:
        conn.execute(
            "INSERT INTO operational.account_lifecycle_proofs "
            "(id,account_id,token_digest,purpose,destination,expires_at,created_at) "
            "SELECT %s,account_id,%s,purpose,destination,expires_at,created_at "
            "FROM operational.account_lifecycle_proofs WHERE account_id=%s "
            "AND purpose='reset_password' LIMIT 1",
            (uuid4(), uuid4().hex * 2, account_id),
        )

    def consume(_):
        try:
            build(ResetPasswordService).execute(
                ResetPasswordRequest(message.token, "ResetNow!12345", str(uuid4()))
            )
            return True
        except LifecycleProofError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume, range(2))) == [False, True]
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.sessions WHERE account_id=%s AND revoked_at IS NULL",
                (account_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.account_lifecycle_proofs WHERE account_id=%s AND purpose=\x27reset_password\x27 AND NOT superseded AND consumed_at IS NULL",
                (account_id,),
            ).fetchone()[0]
            == 0
        )
    security = (
        build(GetAccountSecurityService)
        .execute(GetAccountSecurityRequest(Principal(account_id, user_id)))
        .security
    )
    assert security.recovery_email == request.email and security.email_verified
    with pytest.raises(LifecycleConflictError):
        build(EnrollRecoveryEmailService).execute(
            EnrollRecoveryEmailRequest(Principal(account_id, user_id))
        )
    with pytest.raises(AuthorizationError):
        build(GetAccountSecurityService).execute(
            GetAccountSecurityRequest(Principal(account_id, uuid4()))
        )


def test_initial_trusted_enrollment_snapshots_contact_and_missing_identity_fails_closed(
    lifecycle_database_url,
):
    url = lifecycle_database_url
    build, cipher, request, account_id, user_id = _signup(url)
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.account_recovery_identity SET verification_required=false,pending_email=NULL WHERE account_id=%s",
            (account_id,),
        )
        conn.execute(
            "DELETE FROM operational.lifecycle_mail_outbox WHERE account_id=%s",
            (account_id,),
        )
        conn.execute(
            "UPDATE operational.users SET email=\x27enrollment@example.test\x27 WHERE id=%s",
            (user_id,),
        )
    build(EnrollRecoveryEmailService).execute(
        EnrollRecoveryEmailRequest(Principal(account_id, user_id))
    )
    message = queued(url, cipher, account_id, "verify_email")
    assert message.recipient == "enrollment@example.test"
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.users SET email=\x27changed@example.test\x27 WHERE id=%s",
            (user_id,),
        )
    build(VerifyEmailService).execute(VerifyEmailRequest(message.token, str(uuid4())))
    assert (
        build(GetAccountSecurityService)
        .execute(GetAccountSecurityRequest(Principal(account_id, user_id)))
        .security.recovery_email
        == message.recipient
    )
    with psycopg.connect(url) as conn:
        conn.execute(
            "DELETE FROM operational.account_recovery_identity WHERE account_id=%s",
            (account_id,),
        )
    assert (
        build(ForgotPasswordService)
        .execute(ForgotPasswordRequest(request.email, str(uuid4())))
        .message
        == "Check your email for next steps"
    )


def test_concurrent_duplicate_signup_returns_receipts_without_partial_rows(
    lifecycle_database_url,
):
    url = lifecycle_database_url
    from threading import Barrier

    barrier = Barrier(2)
    from huginn.management.persistence.repositories.account import (
        PostgresAccountRepository,
    )

    class RaceAccounts(PostgresAccountRepository):
        def get_by_normalized_username(self, username):
            result = super().get_by_normalized_username(username)
            barrier.wait(timeout=10)
            return result

    build, _ = services(url, accounts_factory=lambda uow: RaceAccounts(uow.connection))
    request = signup_request()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: build(SignupService).execute(request), range(2))
        )
    assert responses[0] == responses[1]
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.accounts WHERE username=%s",
                (request.username,),
            ).fetchone()[0]
            == 1
        )
        account_id = account(url, request.username)[0]
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.users WHERE account_id=%s",
                (account_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.lifecycle_mail_outbox WHERE account_id=%s",
                (account_id,),
            ).fetchone()[0]
            == 1
        )


def test_outbox_write_failure_rolls_back_signup(lifecycle_database_url):
    from huginn.management.persistence.repositories.lifecycle_mail_outbox import (
        PostgresLifecycleMailOutboxRepository,
    )

    class BrokenOutbox(PostgresLifecycleMailOutboxRepository):
        def enqueue(self, record):
            super().enqueue(record)
            raise RuntimeError("outbox unavailable")

    url = lifecycle_database_url
    build, _ = services(url, outbox_factory=lambda uow: BrokenOutbox(uow.connection))
    request = signup_request()
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        build(SignupService).execute(request)
    assert account(url, request.username) is None


def test_reset_revocation_failure_rolls_back_hash_and_proof(lifecycle_database_url):
    from huginn.management.persistence.repositories.session import (
        PostgresSessionRepository,
    )

    class BrokenSessions(PostgresSessionRepository):
        def revoke_for_account(self, account_id, now):
            super().revoke_for_account(account_id, now)
            raise RuntimeError("revocation unavailable")

    url = lifecycle_database_url
    build, cipher, request, account_id, _ = _signup(url)
    _verify(build, cipher, url, account_id)
    build(ForgotPasswordService).execute(
        ForgotPasswordRequest(request.email, str(uuid4()))
    )
    message = queued(url, cipher, account_id, "reset_password")
    broken, _ = services(
        url,
        sessions_factory=lambda uow: BrokenSessions(uow.connection),
        hash_password_fn=lambda _: "new-hash",
    )
    with pytest.raises(RuntimeError, match="revocation unavailable"):
        broken(ResetPasswordService).execute(
            ResetPasswordRequest(message.token, "ResetNow!12345", str(uuid4()))
        )
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT password_hash FROM operational.accounts WHERE id=%s",
                (account_id,),
            ).fetchone()[0]
            == "test-password-hash"
        )
        assert conn.execute(
            "SELECT consumed_at,superseded FROM operational.account_lifecycle_proofs WHERE account_id=%s AND purpose=\x27reset_password\x27",
            (account_id,),
        ).fetchone() == (None, False)
    build(ResetPasswordService).execute(
        ResetPasswordRequest(message.token, "ResetNow!12345", str(uuid4()))
    )


def test_proof_ip_limits_commit_for_invalid_links(lifecycle_database_url):
    url = lifecycle_database_url
    build, _ = services(url)
    ip = str(uuid4())
    for _ in range(10):
        with pytest.raises(LifecycleProofError):
            build(VerifyEmailService).execute(VerifyEmailRequest("invalid", ip))
    with pytest.raises(LifecycleRateLimitError) as error:
        build(VerifyEmailService).execute(VerifyEmailRequest("invalid", ip))
    assert 1 <= error.value.retry_after_seconds <= 60


def test_forgot_unknown_pending_verified_disabled_have_same_receipt(
    lifecycle_database_url,
):
    url = lifecycle_database_url
    build, cipher, request, account_id, _ = _signup(url)
    pending = build(ForgotPasswordService).execute(
        ForgotPasswordRequest(request.email, str(uuid4()))
    )
    unknown = build(ForgotPasswordService).execute(
        ForgotPasswordRequest(f"{uuid4()}@example.test", str(uuid4()))
    )
    _verify(build, cipher, url, account_id)
    verified = build(ForgotPasswordService).execute(
        ForgotPasswordRequest(request.email, str(uuid4()))
    )
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.accounts SET status=\x27disabled\x27 WHERE id=%s",
            (account_id,),
        )
    disabled = build(ForgotPasswordService).execute(
        ForgotPasswordRequest(request.email, str(uuid4()))
    )
    assert pending == unknown == verified == disabled
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.lifecycle_mail_outbox WHERE account_id=%s AND purpose=\x27reset_password\x27",
                (account_id,),
            ).fetchone()[0]
            == 1
        )


def test_unknown_and_known_usernames_share_admission_limits(lifecycle_database_url):
    url = lifecycle_database_url
    build, _, request, _, _ = _signup(url)
    for username in (request.email, f"{uuid4()}@example.test"):
        ip = str(uuid4())
        for _ in range(4 if username == request.email else 5):
            build(ForgotPasswordService).execute(ForgotPasswordRequest(username, ip))
        with pytest.raises(LifecycleRateLimitError):
            build(ForgotPasswordService).execute(ForgotPasswordRequest(username, ip))
    ip = str(uuid4())
    for _ in range(20):
        build(ForgotPasswordService).execute(
            ForgotPasswordRequest(f"{uuid4()}@example.test", ip)
        )
    with pytest.raises(LifecycleRateLimitError):
        build(ForgotPasswordService).execute(
            ForgotPasswordRequest(f"{uuid4()}@example.test", ip)
        )


def test_replacement_supersedes_old_proof_and_reset_hashes_before_lookup(
    lifecycle_database_url,
):
    url = lifecycle_database_url
    now = [datetime.now(UTC)]
    build, cipher, request, account_id, _ = _signup(url, clock=lambda: now[0])
    old = queued(url, cipher, account_id, "verify_email")
    now[0] += timedelta(seconds=61)
    build(ResendVerificationService).execute(
        ResendVerificationRequest(request.email, str(uuid4()))
    )
    new = queued(url, cipher, account_id, "verify_email")
    assert old.token != new.token
    with pytest.raises(LifecycleProofError):
        build(VerifyEmailService).execute(VerifyEmailRequest(old.token, str(uuid4())))
    build(VerifyEmailService).execute(VerifyEmailRequest(new.token, str(uuid4())))
    calls = []
    hasher, _ = services(
        url, hash_password_fn=lambda password: calls.append(password) or "new-hash"
    )
    with pytest.raises(LifecycleProofError):
        hasher(ResetPasswordService).execute(
            ResetPasswordRequest("missing", "ResetNow!12345", str(uuid4()))
        )
    assert len(calls) == 1
