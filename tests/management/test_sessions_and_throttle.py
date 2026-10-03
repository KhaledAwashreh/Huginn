from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest

from huginn.management.errors.domain import RateLimitError
from huginn.management.security.tokens import digest_token, generate_token
from huginn.management.throttle import FailedLoginThrottle


def test_session_tokens_are_opaque_and_stored_as_digests():
    session_token, csrf_token = generate_token(), generate_token()
    assert session_token != csrf_token
    assert session_token not in digest_token(session_token)
    assert csrf_token not in digest_token(csrf_token)
    assert digest_token(session_token) != digest_token(csrf_token)


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
