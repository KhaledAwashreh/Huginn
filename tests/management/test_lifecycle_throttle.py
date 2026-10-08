from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Lock
from uuid import uuid4

import psycopg
import pytest

from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.lifecycle_throttle import (
    PostgresLifecycleThrottleRepository,
)


def _digest() -> str:
    return sha256(str(uuid4()).encode()).hexdigest()


class _UnexpectedDatabase:
    def __init__(self):
        self.cursor_calls = 0
        self.lock = Lock()

    def cursor(self):
        with self.lock:
            self.cursor_calls += 1
        raise AssertionError("invalid throttle inputs must fail before SQL")


@pytest.mark.parametrize(
    ("scope", "key_digest", "now", "limit", "window"),
    (
        (
            "unknown",
            "a" * 64,
            datetime(2026, 1, 1, tzinfo=UTC),
            1,
            timedelta(minutes=1),
        ),
        (
            "proof_ip",
            "not-a-digest",
            datetime(2026, 1, 1, tzinfo=UTC),
            1,
            timedelta(minutes=1),
        ),
        ("proof_ip", "a" * 64, datetime(2026, 1, 1), 1, timedelta(minutes=1)),
        (
            "proof_ip",
            "a" * 64,
            datetime(2026, 1, 1, tzinfo=UTC),
            0,
            timedelta(minutes=1),
        ),
        (
            "proof_ip",
            "a" * 64,
            datetime(2026, 1, 1, tzinfo=UTC),
            2**31,
            timedelta(minutes=1),
        ),
        ("proof_ip", "a" * 64, datetime(2026, 1, 1, tzinfo=UTC), 1, timedelta(0)),
    ),
)
def test_invalid_reservation_inputs_fail_before_database_access(
    scope, key_digest, now, limit, window
):
    database = _UnexpectedDatabase()
    repository = PostgresLifecycleThrottleRepository(database)

    with pytest.raises(ValueError):
        repository.reserve(scope, key_digest, now, limit=limit, window=window)

    assert database.cursor_calls == 0


def test_live_throttle_admits_limit_then_resets_at_fixed_window_boundary(
    management_database_url,
):
    scope = "receipt_username"
    key_digest = _digest()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    window = timedelta(minutes=10)
    try:
        with psycopg.connect(management_database_url) as connection:
            repository = PostgresLifecycleThrottleRepository(
                PsycopgDatabaseSession(connection)
            )

            first = repository.reserve(scope, key_digest, start, limit=2, window=window)
            second = repository.reserve(
                scope, key_digest, start + timedelta(seconds=2), limit=2, window=window
            )
            denied = repository.reserve(
                scope, key_digest, start + timedelta(seconds=3), limit=2, window=window
            )
            almost_expired = repository.reserve(
                scope,
                key_digest,
                start + window - timedelta(milliseconds=900),
                limit=2,
                window=window,
            )
            reset = repository.reserve(
                scope, key_digest, start + window, limit=2, window=window
            )

            assert (first.allowed, first.retry_after_seconds) == (True, 0)
            assert (second.allowed, second.retry_after_seconds) == (True, 0)
            assert (denied.allowed, denied.retry_after_seconds) == (False, 597)
            assert (almost_expired.allowed, almost_expired.retry_after_seconds) == (
                False,
                1,
            )
            assert (reset.allowed, reset.retry_after_seconds) == (True, 0)

            persisted = connection.execute(
                "SELECT scope, key_digest, window_started_at, request_count "
                "FROM operational.lifecycle_throttle "
                "WHERE scope = %s AND key_digest = %s",
                (scope, key_digest),
            ).fetchone()
            assert persisted == (scope, key_digest, start + window, 1)
    finally:
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DELETE FROM operational.lifecycle_throttle "
                "WHERE scope = %s AND key_digest = %s",
                (scope, key_digest),
            )


def test_live_concurrent_reservations_admit_only_the_configured_limit(
    management_database_url,
):
    scope = "proof_ip"
    key_digest = _digest()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    limit = 5
    window = timedelta(minutes=1)

    def reserve_once():
        with psycopg.connect(management_database_url) as connection:
            return PostgresLifecycleThrottleRepository(
                PsycopgDatabaseSession(connection)
            ).reserve(scope, key_digest, now, limit=limit, window=window)

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            reservations = list(executor.map(lambda _: reserve_once(), range(20)))

        assert sum(reservation.allowed for reservation in reservations) == limit
        assert all(
            reservation.retry_after_seconds == 0
            for reservation in reservations
            if reservation.allowed
        )
        assert all(
            reservation.retry_after_seconds == 60
            for reservation in reservations
            if not reservation.allowed
        )
        with psycopg.connect(management_database_url) as connection:
            persisted = connection.execute(
                "SELECT request_count FROM operational.lifecycle_throttle "
                "WHERE scope = %s AND key_digest = %s",
                (scope, key_digest),
            ).fetchone()
        assert persisted == (20,)
    finally:
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DELETE FROM operational.lifecycle_throttle "
                "WHERE scope = %s AND key_digest = %s",
                (scope, key_digest),
            )
