from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from uuid import uuid4

import pytest

from huginn.management.domain import RateLimitError, Session
from huginn.management.identity import SessionService
from huginn.management.throttle import FailedLoginThrottle


class FakeSessionRepository:
    def __init__(self):
        self.rows = {}

    def create(self, value):
        row = Session(
            uuid4(),
            value.account_id,
            value.token_digest,
            value.csrf_digest,
            datetime(2026, 1, 1, tzinfo=UTC),
            value.expires_at,
            None,
        )
        self.rows[value.token_digest] = row
        return row

    def get_by_token_digest(self, digest):
        return self.rows.get(digest)

    def revoke_current(self, session_id, revoked_at):
        for digest, row in self.rows.items():
            if row.id == session_id:
                self.rows[digest] = replace(row, revoked_at=revoked_at)

    def revoke_for_account(self, account_id, revoked_at):
        for digest, row in self.rows.items():
            if row.account_id == account_id:
                self.rows[digest] = replace(row, revoked_at=revoked_at)


def test_session_service_generates_injectable_opaque_tokens_and_stores_digests():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    tokens = iter(("opaque-session-token", "opaque-csrf-token"))
    repository = FakeSessionRepository()
    service = SessionService(
        repository,
        clock=lambda: now,
        ttl=timedelta(hours=12),
        token_generator=lambda: next(tokens),
    )

    issued = service.create(uuid4())

    assert (issued.session_token, issued.csrf_token) == (
        "opaque-session-token",
        "opaque-csrf-token",
    )
    assert issued.session_token not in repr(repository.rows)
    assert issued.csrf_token not in repr(repository.rows)
    assert issued.session_token not in repr(issued)
    assert issued.csrf_token not in repr(issued)
    assert service.resolve(issued.session_token).account_id == issued.account_id


def test_session_service_rejects_expired_and_revoked_sessions():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    repository = FakeSessionRepository()
    tokens = iter(f"opaque-{index}" for index in range(4))
    service = SessionService(
        repository,
        clock=lambda: now,
        ttl=timedelta(seconds=1),
        token_generator=lambda: next(tokens),
    )
    expired = service.create(uuid4())
    now += timedelta(seconds=2)
    assert service.resolve(expired.session_token) is None

    now = datetime(2026, 1, 1, tzinfo=UTC)
    active = service.create(uuid4())
    service.revoke_current(active.session_token)
    assert service.resolve(active.session_token) is None
    service.revoke_account(active.account_id)


def test_failed_login_throttle_uses_lower_normalized_composite_key_and_resets():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    throttle = FailedLoginThrottle(
        clock=lambda: now, max_failures=2, window=timedelta(minutes=15)
    )
    throttle.record_failure("192.0.2.1", " Ada ")
    throttle.record_failure("192.0.2.1", "ada")
    assert throttle.is_limited("192.0.2.1", "ADA")
    assert not throttle.is_limited("192.0.2.2", "ada")
    assert not throttle.is_limited("192.0.2.1", "other")
    throttle.record_success("192.0.2.1", "Ada")
    assert not throttle.is_limited("192.0.2.1", "ada")
    throttle.record_failure("192.0.2.1", "ada")
    now += timedelta(minutes=15)
    assert not throttle.is_limited("192.0.2.1", "ada")


def test_failed_login_throttle_limit_error_does_not_disclose_key():
    throttle = FailedLoginThrottle(max_failures=1)
    throttle.record_failure("private-ip", "private-user")
    with pytest.raises(RateLimitError) as caught:
        throttle.check("private-ip", "private-user")
    assert "private-ip" not in str(caught.value)
    assert "private-user" not in str(caught.value)


def test_failed_login_throttle_reserves_only_five_concurrent_attempts():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    throttle = FailedLoginThrottle(
        clock=lambda: now,
        max_failures=5,
        window=timedelta(minutes=15),
    )
    barrier = Barrier(41)
    reservations, rejected = [], []

    def reserve_login():
        barrier.wait()
        try:
            reservations.append(throttle.reserve("192.0.2.1", "ada"))
        except RateLimitError:
            rejected.append(True)

    threads = [Thread(target=reserve_login) for _ in range(40)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert len(reservations) == 5
    assert len(rejected) == 35
    assert throttle.is_limited("192.0.2.1", "ada")
    for reservation in reservations:
        throttle.release(reservation)


def test_failed_login_reservation_success_reset_and_window_expiry():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    throttle = FailedLoginThrottle(
        clock=lambda: now,
        max_failures=2,
        window=timedelta(minutes=15),
    )
    first = throttle.reserve("192.0.2.1", "Ada")
    throttle.record_failure("192.0.2.1", "Ada", first)
    second = throttle.reserve("192.0.2.1", "ada")
    throttle.record_success("192.0.2.1", "ADA", second)
    assert not throttle.is_limited("192.0.2.1", "ada")

    throttle.record_failure("192.0.2.1", "ada")
    throttle.record_failure("192.0.2.1", "ada")
    assert throttle.is_limited("192.0.2.1", "ada")
    assert not throttle.is_limited("192.0.2.2", "ada")
    assert not throttle.is_limited("192.0.2.1", "other")
    now += timedelta(minutes=15)
    assert not throttle.is_limited("192.0.2.1", "ada")
