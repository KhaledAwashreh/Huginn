"""Durable lifecycle claims and fenced settlement on disposable PostgreSQL 16."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.read_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRecord,
)
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.persistence.repositories.lifecycle_mail_outbox import (
    PostgresLifecycleMailOutboxRepository,
)
from tests.postgres_harness import provisioned_postgres


@pytest.fixture
def outbox_database_url():
    with provisioned_postgres("huginn_lifecycle_outbox") as url:
        yield url


def _enqueue(conn, now, *, expires_at=None, account_id=None):
    account_id = account_id or uuid4()
    proof_id = uuid4()
    conn.execute(
        "INSERT INTO operational.accounts (id,username,password_hash) "
        "VALUES (%s,%s,'hash') ON CONFLICT DO NOTHING",
        (account_id, str(account_id)),
    )
    conn.execute(
        "INSERT INTO operational.account_recovery_identity "
        "(account_id,verification_required,pending_email) "
        "VALUES (%s,true,'recipient@example.com') ON CONFLICT DO NOTHING",
        (account_id,),
    )
    conn.execute(
        "INSERT INTO operational.account_lifecycle_proofs "
        "(id,account_id,token_digest,purpose,destination,expires_at,created_at) "
        "VALUES (%s,%s,%s,'verify_email','recipient@example.com',%s,%s)",
        (
            proof_id,
            account_id,
            uuid4().hex * 2,
            expires_at or now + timedelta(days=1),
            now,
        ),
    )
    record = LifecycleMailOutboxRecord(
        uuid4(), account_id, proof_id, "verify_email", b"opaque-ciphertext", now
    )
    PostgresLifecycleMailOutboxRepository(conn).enqueue(record)
    return record


def _delivery(conn, mail_id):
    return conn.execute(
        "SELECT state,attempt_count,encrypted_payload,claim_token,claimed_at,"
        "lease_until,failure_code,sent_at,next_attempt_at "
        "FROM operational.lifecycle_mail_outbox WHERE id=%s",
        (mail_id,),
    ).fetchone()


def test_competing_workers_claim_distinct_rows_without_waiting(outbox_database_url):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as setup:
        records = [_enqueue(setup, now), _enqueue(setup, now)]
    with (
        psycopg.connect(outbox_database_url) as first,
        psycopg.connect(outbox_database_url) as second,
    ):
        second.execute("SET LOCAL statement_timeout='2s'")
        claim1 = PostgresLifecycleMailOutboxRepository(first).claim_due(
            now, lease_seconds=120, max_attempts=5
        )
        claim2 = PostgresLifecycleMailOutboxRepository(second).claim_due(
            now, lease_seconds=120, max_attempts=5
        )
        assert claim1 is not None and claim2 is not None
        assert {claim1.id, claim2.id} == {record.id for record in records}
        assert claim1.claim_token != claim2.claim_token
        assert claim1.attempt_count == claim2.attempt_count == 1
        assert claim1.encrypted_payload == b"opaque-ciphertext"
        assert claim1.lease_until > now


def test_claim_rollback_releases_work_and_retry_preserves_ciphertext(
    outbox_database_url,
):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as conn:
        record = _enqueue(conn, now)
        conn.commit()
        repo = PostgresLifecycleMailOutboxRepository(conn)
        abandoned = repo.claim_due(now, lease_seconds=120, max_attempts=5)
        assert abandoned is not None
        conn.rollback()
        claim = repo.claim_due(now, lease_seconds=120, max_attempts=5)
        assert claim is not None
        assert claim.id == record.id
        assert claim.attempt_count == 1
        assert claim.claim_token != abandoned.claim_token
        retry_at = now + timedelta(minutes=2)
        assert repo.settle(
            claim,
            now,
            state="pending",
            failure_code="transport_unavailable",
            next_attempt_at=retry_at,
        )
        row = _delivery(conn, record.id)
        assert row[:7] == (
            "pending",
            1,
            b"opaque-ciphertext",
            None,
            None,
            None,
            "transport_unavailable",
        )
        assert row[8] == retry_at
        assert repo.claim_due(now, lease_seconds=120, max_attempts=5) is None


def test_crashed_fifth_claim_exhausts_budget_and_scrubs_payload(outbox_database_url):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as conn:
        record = _enqueue(conn, now)
        conn.execute(
            "UPDATE operational.lifecycle_mail_outbox SET attempt_count=4 WHERE id=%s",
            (record.id,),
        )
        repo = PostgresLifecycleMailOutboxRepository(conn)
        claim = repo.claim_due(now, lease_seconds=120, max_attempts=5)
        assert claim is not None and claim.attempt_count == 5
        conn.commit()
        assert (
            repo.claim_due(
                claim.lease_until + timedelta(seconds=1),
                lease_seconds=120,
                max_attempts=5,
            )
            is None
        )
        assert _delivery(conn, record.id)[:8] == (
            "failed",
            5,
            None,
            None,
            None,
            None,
            "attempts_exhausted",
            None,
        )


def test_stale_worker_cannot_settle_reclaimed_or_expired_claim(outbox_database_url):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as conn:
        record = _enqueue(conn, now)
        repo = PostgresLifecycleMailOutboxRepository(conn)
        stale = repo.claim_due(now, lease_seconds=120, max_attempts=5)
        assert stale is not None
        conn.commit()
        later = stale.lease_until + timedelta(seconds=1)
        assert not repo.settle(stale, later, state="sent")
        current = repo.claim_due(later, lease_seconds=120, max_attempts=5)
        assert current is not None and current.attempt_count == 2
        conn.commit()
        assert not repo.settle(stale, later, state="sent")
        assert _delivery(conn, record.id)[3] == current.claim_token
        assert repo.settle(current, later, state="sent")
        assert _delivery(conn, record.id)[:7] == (
            "sent",
            2,
            None,
            None,
            None,
            None,
            None,
        )
        assert not repo.settle(
            current, later, state="failed", failure_code="invalid_payload"
        )


def test_expired_proof_is_scrubbed_without_claiming_active_worker(outbox_database_url):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as conn:
        record = _enqueue(conn, now, expires_at=now + timedelta(seconds=10))
        repo = PostgresLifecycleMailOutboxRepository(conn)
        claim = repo.claim_due(now, lease_seconds=120, max_attempts=5)
        assert claim is not None
        assert (
            repo.claim_due(
                now + timedelta(seconds=20), lease_seconds=120, max_attempts=5
            )
            is None
        )
        assert _delivery(conn, record.id)[0] == "claimed"
        assert (
            repo.claim_due(
                claim.lease_until + timedelta(seconds=1),
                lease_seconds=120,
                max_attempts=5,
            )
            is None
        )
        assert _delivery(conn, record.id)[:8] == (
            "failed",
            1,
            None,
            None,
            None,
            None,
            "expired_proof",
            None,
        )


@pytest.mark.parametrize("state", ["sent", "failed", "suppressed"])
def test_terminal_settlement_scrubs_secret_and_claim_metadata(
    outbox_database_url, state
):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as conn:
        record = _enqueue(conn, now)
        repo = PostgresLifecycleMailOutboxRepository(conn)
        claim = repo.claim_due(now, lease_seconds=120, max_attempts=5)
        assert claim is not None
        failure_code = None if state == "sent" else "obsolete_proof"
        assert repo.settle(claim, now, state=state, failure_code=failure_code)
        row = _delivery(conn, record.id)
        assert row[:7] == (state, 1, None, None, None, None, failure_code)
        assert (row[7] is not None) == (state == "sent")


def test_cooldown_uses_latest_enqueue_for_exact_account_and_purpose(
    outbox_database_url,
):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as conn:
        repo = PostgresLifecycleMailOutboxRepository(conn)
        assert repo.last_enqueued_at(uuid4(), ProofPurpose.VERIFY_EMAIL) is None
        record = _enqueue(conn, now)
        newer = _enqueue(conn, now, account_id=record.account_id)
        latest = now + timedelta(seconds=1)
        conn.execute(
            "UPDATE operational.lifecycle_mail_outbox SET created_at=%s WHERE id=%s",
            (now - timedelta(minutes=1), record.id),
        )
        conn.execute(
            "UPDATE operational.lifecycle_mail_outbox SET created_at=%s WHERE id=%s",
            (latest, newer.id),
        )
        assert (
            repo.last_enqueued_at(record.account_id, ProofPurpose.VERIFY_EMAIL)
            == latest
        )
        assert (
            repo.last_enqueued_at(record.account_id, ProofPurpose.RESET_PASSWORD)
            is None
        )


def test_settlement_rechecks_real_clock_after_waiting_for_row_lock(outbox_database_url):
    now = datetime.now(UTC)
    with psycopg.connect(outbox_database_url) as setup:
        record = _enqueue(setup, now)
        claim = PostgresLifecycleMailOutboxRepository(setup).claim_due(
            now, lease_seconds=1, max_attempts=5
        )
        assert claim is not None
    with (
        psycopg.connect(outbox_database_url) as blocker,
        psycopg.connect(
            outbox_database_url, application_name="lifecycle_fenced_settlement"
        ) as worker,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        blocker.execute(
            "SELECT id FROM operational.lifecycle_mail_outbox WHERE id=%s FOR UPDATE",
            (record.id,),
        )
        future = pool.submit(
            PostgresLifecycleMailOutboxRepository(worker).settle,
            claim,
            now,
            state="sent",
        )
        try:
            deadline = monotonic() + 5
            blocked = False
            while monotonic() < deadline:
                blocked = blocker.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name='lifecycle_fenced_settlement' "
                    "AND wait_event_type='Lock')"
                ).fetchone()[0]
                if blocked:
                    break
                sleep(0.01)
            assert blocked, "settlement did not contend on the held delivery row"
            blocker.execute(
                "SELECT pg_sleep(GREATEST(0,EXTRACT(epoch FROM "
                "(%s::timestamptz-clock_timestamp()))) + 0.1)",
                (claim.lease_until,),
            )
        finally:
            blocker.rollback()
        assert future.result(timeout=5) is False
        assert _delivery(worker, record.id)[0] == "claimed"
