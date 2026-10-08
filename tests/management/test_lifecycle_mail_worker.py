"""Delivery policy and worker process behavior with isolated PostgreSQL 16."""

import logging
import signal
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest
from cryptography.fernet import Fernet

from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)
from huginn.management.application.read_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRecord,
)
from huginn.management.application.requests.deliver_lifecycle_mail_request import (
    DeliverLifecycleMailRequest,
)
from huginn.management.application.responses.deliver_lifecycle_mail_response import (
    DeliverLifecycleMailResponse,
)
from huginn.management.application.services.deliver_lifecycle_mail_service import (
    DeliverLifecycleMailService,
)
from huginn.management.config import ManagementConfig
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.errors.database import DatabaseError
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.account_lifecycle_proof import (
    PostgresAccountLifecycleProofRepository,
)
from huginn.management.persistence.repositories.account_recovery_identity import (
    PostgresAccountRecoveryIdentityRepository,
)
from huginn.management.persistence.repositories.lifecycle_mail_outbox import (
    PostgresLifecycleMailOutboxRepository,
)
from huginn.management.presentation.cli.lifecycle_mail_worker import (
    _build_service,
    main,
)
from huginn.management.security.encrypted_proof_cipher import EncryptedProofCipher
from huginn.management.security.lifecycle_proofs import (
    digest_lifecycle_proof,
    generate_lifecycle_proof,
)
from tests.postgres_harness import provisioned_postgres


@pytest.fixture
def worker_database_url():
    with provisioned_postgres("huginn_lifecycle_mail_worker") as url:
        yield url


class _Sender:
    def __init__(self, action):
        self.action = action
        self.messages = []

    def send(self, message):
        self.action(message)
        self.messages.append(message)


def _setup(url, *, purpose="verify_email", attempts=0, payload=None):
    now = datetime.now(UTC)
    account_id, proof_id, mail_id = uuid4(), uuid4(), uuid4()
    cipher = EncryptedProofCipher(Fernet.generate_key())
    message = LifecycleMailMessage(
        "private-recipient@example.com", purpose, generate_lifecycle_proof()
    )
    with psycopg.connect(url) as conn:
        conn.execute(
            "INSERT INTO operational.accounts(id,username,password_hash) VALUES (%s,%s,'hash')",
            (account_id, str(account_id)),
        )
        conn.execute(
            "INSERT INTO operational.account_recovery_identity "
            "(account_id,verification_required,pending_email,verified_email,verified_at) "
            "VALUES (%s,true,%s,%s,%s)",
            (
                account_id,
                message.recipient if purpose == "verify_email" else None,
                message.recipient if purpose == "reset_password" else None,
                now if purpose == "reset_password" else None,
            ),
        )
        conn.execute(
            "INSERT INTO operational.account_lifecycle_proofs "
            "(id,account_id,token_digest,purpose,destination,expires_at,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                proof_id,
                account_id,
                digest_lifecycle_proof(message.token),
                purpose,
                message.recipient,
                now + timedelta(days=1),
                now,
            ),
        )
        PostgresLifecycleMailOutboxRepository(conn).enqueue(
            LifecycleMailOutboxRecord(
                mail_id,
                account_id,
                proof_id,
                purpose,
                payload or cipher.encrypt(message),
                now,
            )
        )
        conn.execute(
            "UPDATE operational.lifecycle_mail_outbox SET attempt_count=%s WHERE id=%s",
            (attempts, mail_id),
        )
    return now, account_id, proof_id, mail_id, message, cipher


def _service(url, cipher, sender, *, clock=None, tracker=None):
    factory = ManagementConnectionFactory(url)
    tracker = tracker if tracker is not None else {"active": 0}

    @contextmanager
    def uow_factory():
        tracker["active"] += 1
        try:
            with UnitOfWork(factory) as uow:
                yield uow
        finally:
            tracker["active"] -= 1

    return DeliverLifecycleMailService(
        uow_factory,
        cipher=cipher,
        sender=sender,
        clock=clock,
        outbox_factory=lambda uow: PostgresLifecycleMailOutboxRepository(
            uow.connection
        ),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        recovery_identities_factory=lambda uow: (
            PostgresAccountRecoveryIdentityRepository(uow.connection)
        ),
        proofs_factory=lambda uow: PostgresAccountLifecycleProofRepository(
            uow.connection
        ),
    )


def _row(url, mail_id):
    with psycopg.connect(url) as conn:
        return conn.execute(
            "SELECT state,encrypted_payload,claim_token,failure_code,attempt_count,next_attempt_at "
            "FROM operational.lifecycle_mail_outbox WHERE id=%s",
            (mail_id,),
        ).fetchone()


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
def test_smtp_sees_committed_claim_outside_all_uow_contexts(
    worker_database_url, purpose
):
    url = worker_database_url
    _, _, _, mail_id, expected, cipher = _setup(url, purpose=purpose)
    tracker = {"active": 0}

    def send(message):
        assert tracker["active"] == 0
        row = _row(url, mail_id)
        assert row[0] == "claimed" and row[2] is not None and row[4] == 1
        assert message == expected

    sender = _Sender(send)
    result = _service(url, cipher, sender, tracker=tracker).execute(
        DeliverLifecycleMailRequest()
    )
    assert result == DeliverLifecycleMailResponse(mail_id, "sent")
    assert _row(url, mail_id)[:4] == ("sent", None, None, None)


@pytest.mark.parametrize(
    "obsolete", ["superseded", "consumed", "disabled", "destination"]
)
def test_known_obsolete_messages_are_suppressed_and_scrubbed(
    worker_database_url, obsolete
):
    url = worker_database_url
    _, account_id, proof_id, mail_id, _, cipher = _setup(url)
    with psycopg.connect(url) as conn:
        if obsolete == "superseded":
            conn.execute(
                "UPDATE operational.account_lifecycle_proofs SET superseded=true WHERE id=%s",
                (proof_id,),
            )
        elif obsolete == "consumed":
            conn.execute(
                "UPDATE operational.account_lifecycle_proofs SET consumed_at=now() WHERE id=%s",
                (proof_id,),
            )
        elif obsolete == "disabled":
            conn.execute(
                "UPDATE operational.accounts SET status='disabled' WHERE id=%s",
                (account_id,),
            )
        else:
            conn.execute(
                "UPDATE operational.account_recovery_identity SET pending_email='other@example.com' WHERE account_id=%s",
                (account_id,),
            )
    sender = _Sender(lambda message: pytest.fail("obsolete mail was sent"))
    result = _service(url, cipher, sender).execute(DeliverLifecycleMailRequest())
    assert result.outcome == "suppressed"
    assert _row(url, mail_id)[:4] == ("suppressed", None, None, "obsolete_proof")


def test_expiry_between_claim_and_snapshot_is_suppressed(worker_database_url):
    url = worker_database_url
    now, _, proof_id, mail_id, _, cipher = _setup(url)
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.account_lifecycle_proofs SET expires_at=%s WHERE id=%s",
            (now + timedelta(seconds=10), proof_id),
        )
    times = iter([now, now + timedelta(seconds=20), now + timedelta(seconds=20)])
    sender = _Sender(lambda message: pytest.fail("expired mail was sent"))
    result = _service(url, cipher, sender, clock=lambda: next(times)).execute(
        DeliverLifecycleMailRequest()
    )
    assert result.outcome == "suppressed"
    assert _row(url, mail_id)[:4] == ("suppressed", None, None, "expired_proof")


@pytest.mark.parametrize("fault", ["ciphertext", "recipient", "purpose", "token"])
def test_invalid_envelope_is_terminal_without_secret_logs(
    worker_database_url, caplog, fault
):
    url = worker_database_url
    _, _, _, mail_id, message, cipher = _setup(url)
    altered = LifecycleMailMessage(
        "attacker@example.com" if fault == "recipient" else message.recipient,
        "reset_password" if fault == "purpose" else message.purpose,
        "wrong-secret-token" if fault == "token" else message.token,
    )
    payload = (
        b"invalid-ciphertext-secret"
        if fault == "ciphertext"
        else cipher.encrypt(altered)
    )
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.lifecycle_mail_outbox SET encrypted_payload=%s WHERE id=%s",
            (payload, mail_id),
        )
    sender = _Sender(lambda message: pytest.fail("invalid payload was sent"))
    with caplog.at_level(logging.INFO):
        result = _service(url, cipher, sender).execute(DeliverLifecycleMailRequest())
    assert result.outcome == "failed"
    assert _row(url, mail_id)[:4] == ("failed", None, None, "invalid_payload")
    assert message.recipient not in caplog.text
    assert message.token not in caplog.text
    assert "invalid-ciphertext-secret" not in caplog.text


@pytest.mark.parametrize(
    "attempts, outcome, state, code",
    [
        (0, "retried", "pending", "transport_unavailable"),
        (4, "failed", "failed", "attempts_exhausted"),
    ],
)
def test_transport_failure_retries_or_exhausts_without_logging_secrets(
    worker_database_url, caplog, attempts, outcome, state, code
):
    url = worker_database_url
    now, _, _, mail_id, message, cipher = _setup(url, attempts=attempts)

    def unavailable(message):
        raise OSError(f"SMTP-password-secret {message.recipient} {message.token}")

    with caplog.at_level(logging.INFO):
        result = _service(url, cipher, _Sender(unavailable), clock=lambda: now).execute(
            DeliverLifecycleMailRequest()
        )
    assert result.outcome == outcome
    row = _row(url, mail_id)
    assert row[0] == state and row[3] == code and row[4] == attempts + 1
    assert (row[1] is None) == (state == "failed")
    if state == "pending":
        assert row[5] == now + timedelta(seconds=60)
    assert message.recipient not in caplog.text and message.token not in caplog.text
    assert "SMTP-password-secret" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_idle_claim_still_commits_expired_payload_cleanup(worker_database_url):
    url = worker_database_url
    now, _, _, mail_id, _, cipher = _setup(url)
    sender = _Sender(lambda message: pytest.fail("expired mail was sent"))
    result = _service(
        url, cipher, sender, clock=lambda: now + timedelta(days=2)
    ).execute(DeliverLifecycleMailRequest())
    assert result == DeliverLifecycleMailResponse(None, "idle")
    assert _row(url, mail_id)[:4] == ("failed", None, None, "expired_proof")


def test_keyboard_interrupt_leaves_claim_recoverable(worker_database_url):
    url = worker_database_url
    _, _, _, mail_id, _, cipher = _setup(url)

    def interrupted(message):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _service(url, cipher, _Sender(interrupted)).execute(
            DeliverLifecycleMailRequest()
        )
    row = _row(url, mail_id)
    assert row[0] == "claimed" and row[1] is not None and row[2] is not None


def test_cli_once_uses_injected_service_without_loading_config():
    calls = []

    class Service:
        def execute(self, request):
            calls.append(request)
            return DeliverLifecycleMailResponse(None, "idle")

    assert main(["--once"], service_factory=Service) == 0
    assert calls == [DeliverLifecycleMailRequest()]


def test_worker_builder_accepts_explicit_config_without_database_io():
    config = ManagementConfig(
        database_url="postgresql://unused:unused@127.0.0.1:1/unused",
        lifecycle_proof_key=Fernet.generate_key().decode(),
        web_origin="http://localhost:5173",
    )
    assert isinstance(_build_service(config), DeliverLifecycleMailService)


def test_cli_failure_hides_exception_text(caplog):
    def unavailable():
        raise ValueError("private-config-password")

    assert main(["--once"], service_factory=unavailable) == 1
    assert "private-config-password" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_cli_shutdown_finishes_current_attempt_without_claiming_another():
    calls = []

    class Service:
        def execute(self, request):
            calls.append(request)
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            return DeliverLifecycleMailResponse(uuid4(), "sent")

    previous = signal.getsignal(signal.SIGTERM)
    assert main(["--poll-seconds", "1"], service_factory=Service) == 0
    assert len(calls) == 1
    assert signal.getsignal(signal.SIGTERM) == previous


def test_expired_claim_cannot_be_settled_after_uncertain_send(worker_database_url):
    url = worker_database_url
    _, _, _, mail_id, _, cipher = _setup(url)

    def send(message):
        with psycopg.connect(url) as conn:
            conn.execute(
                "UPDATE operational.lifecycle_mail_outbox SET claimed_at=now()-interval '3 seconds', "
                "lease_until=now()-interval '1 second' WHERE id=%s",
                (mail_id,),
            )

    result = _service(url, cipher, _Sender(send)).execute(DeliverLifecycleMailRequest())
    assert result == DeliverLifecycleMailResponse(mail_id, "lost_claim")
    row = _row(url, mail_id)
    assert row[0] == "claimed" and row[1] is not None


def test_account_snapshot_lock_wait_is_bounded_and_leaves_claim_recoverable(
    worker_database_url, caplog
):
    url = worker_database_url
    _, account_id, _, mail_id, _, cipher = _setup(url)
    sender = _Sender(lambda message: pytest.fail("locked account mail was sent"))
    with psycopg.connect(url) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute(
            "SELECT id FROM operational.accounts WHERE id=%s FOR UPDATE", (account_id,)
        )
        started = monotonic()
        future = pool.submit(
            _service(url, cipher, sender).execute, DeliverLifecycleMailRequest()
        )
        try:
            result = future.result(timeout=8)
        finally:
            blocker.rollback()
        elapsed = monotonic() - started
    assert result == DeliverLifecycleMailResponse(mail_id, "lost_claim")
    assert elapsed < 8
    assert _row(url, mail_id)[0] == "claimed"
    assert "private-recipient@example.com" not in caplog.text


def test_ownership_is_rechecked_after_decrypt_before_smtp(worker_database_url):
    url = worker_database_url
    _, _, _, mail_id, _, cipher = _setup(url)

    class ReclaimedCipher:
        def decrypt(self, payload):
            message = cipher.decrypt(payload)
            with psycopg.connect(url) as conn:
                conn.execute(
                    "UPDATE operational.lifecycle_mail_outbox SET claim_token=%s WHERE id=%s",
                    (uuid4(), mail_id),
                )
            return message

    sender = _Sender(lambda message: pytest.fail("a lost owner started SMTP"))
    result = _service(url, ReclaimedCipher(), sender).execute(
        DeliverLifecycleMailRequest()
    )
    assert result == DeliverLifecycleMailResponse(mail_id, "lost_claim")
    assert _row(url, mail_id)[0] == "claimed"


def test_lease_expiring_during_decrypt_prevents_smtp_start(worker_database_url):
    url = worker_database_url
    _, _, _, mail_id, _, cipher = _setup(url)

    class ExpiredCipher:
        def decrypt(self, payload):
            message = cipher.decrypt(payload)
            with psycopg.connect(url) as conn:
                conn.execute(
                    "UPDATE operational.lifecycle_mail_outbox SET claimed_at=now()-interval '3 seconds', "
                    "lease_until=now()-interval '1 second' WHERE id=%s",
                    (mail_id,),
                )
            return message

    sender = _Sender(lambda message: pytest.fail("an expired owner started SMTP"))
    result = _service(url, ExpiredCipher(), sender).execute(
        DeliverLifecycleMailRequest()
    )
    assert result == DeliverLifecycleMailResponse(mail_id, "lost_claim")


def test_lease_expired_while_snapshot_waits_prevents_smtp(worker_database_url):
    url = worker_database_url
    _, account_id, _, mail_id, _, cipher = _setup(url)
    sender = _Sender(lambda message: pytest.fail("expired snapshot owner started SMTP"))
    with psycopg.connect(url) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute(
            "SELECT id FROM operational.accounts WHERE id=%s FOR UPDATE", (account_id,)
        )
        future = pool.submit(
            _service(url, cipher, sender).execute, DeliverLifecycleMailRequest()
        )
        try:
            deadline = monotonic() + 3
            while monotonic() < deadline:
                blocker.execute("SELECT pg_stat_clear_snapshot()")
                blocked = blocker.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                    "WHERE datname=current_database() AND wait_event_type='Lock' "
                    "AND query LIKE 'SELECT%operational.accounts%FOR UPDATE%')"
                ).fetchone()[0]
                if blocked:
                    break
                sleep(0.01)
            assert blocked, "snapshot did not wait on the held account"
            blocker.execute(
                "UPDATE operational.lifecycle_mail_outbox "
                "SET claimed_at=now()-interval '3 seconds', "
                "lease_until=now()-interval '1 second' WHERE id=%s",
                (mail_id,),
            )
            blocker.commit()
        finally:
            blocker.rollback()
        result = future.result(timeout=8)
    assert result == DeliverLifecycleMailResponse(mail_id, "lost_claim")
    assert _row(url, mail_id)[0] == "claimed"


def test_ownership_statement_lock_wait_is_bounded(worker_database_url):
    url = worker_database_url
    _, _, _, mail_id, _, cipher = _setup(url)
    sender = _Sender(lambda message: pytest.fail("blocked owner started SMTP"))
    with psycopg.connect(url) as blocker:

        class BlockingCipher:
            def decrypt(self, payload):
                message = cipher.decrypt(payload)
                blocker.execute(
                    "LOCK TABLE operational.lifecycle_mail_outbox IN ACCESS EXCLUSIVE MODE"
                )
                return message

        started = monotonic()
        try:
            result = _service(url, BlockingCipher(), sender).execute(
                DeliverLifecycleMailRequest()
            )
        finally:
            blocker.rollback()
    assert monotonic() - started < 8
    assert result == DeliverLifecycleMailResponse(mail_id, "lost_claim")
    assert _row(url, mail_id)[0] == "claimed"


def test_settlement_lock_wait_is_bounded(worker_database_url):
    url = worker_database_url
    _, _, _, mail_id, _, cipher = _setup(url)
    with psycopg.connect(url) as blocker:

        def send(message):
            blocker.execute(
                "SELECT id FROM operational.lifecycle_mail_outbox WHERE id=%s FOR UPDATE",
                (mail_id,),
            )

        started = monotonic()
        try:
            result = _service(url, cipher, _Sender(send)).execute(
                DeliverLifecycleMailRequest()
            )
        finally:
            blocker.rollback()
    assert monotonic() - started < 8
    assert result == DeliverLifecycleMailResponse(mail_id, "lost_claim")
    assert _row(url, mail_id)[0] == "claimed"


def test_initial_claim_statement_lock_wait_is_bounded(worker_database_url):
    url = worker_database_url
    _, _, _, mail_id, _, cipher = _setup(url)
    sender = _Sender(lambda message: pytest.fail("blocked claim started SMTP"))
    with psycopg.connect(url) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute(
            "LOCK TABLE operational.lifecycle_mail_outbox IN ACCESS EXCLUSIVE MODE"
        )
        started = monotonic()
        future = pool.submit(
            _service(url, cipher, sender).execute, DeliverLifecycleMailRequest()
        )
        try:
            with pytest.raises(DatabaseError) as failure:
                future.result(timeout=8)
            assert failure.value.sqlstate in {"55P03", "57014"}
        finally:
            blocker.rollback()
    assert monotonic() - started < 8
    assert _row(url, mail_id)[0] == "pending"
