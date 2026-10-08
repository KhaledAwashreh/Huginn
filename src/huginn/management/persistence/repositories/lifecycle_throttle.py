"""Persisted fixed-window admission for public account lifecycle requests."""

import re
from datetime import datetime, timedelta
from math import ceil
from typing import Literal

from huginn.management.application.protocols.lifecycle_throttle import (
    LifecycleThrottleRepository,
)
from huginn.management.application.read_models.lifecycle_throttle import (
    LifecycleThrottleReservation,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.repositories.common import PostgresIdentityRepository
from huginn.management.persistence.row_models.lifecycle_throttle import (
    LifecycleThrottleRow,
)

_SCOPES = frozenset({"receipt_username", "receipt_email", "receipt_ip", "proof_ip"})
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_POSTGRES_INTEGER_MAX = 2**31 - 1
_RETURNED_FIELDS = (
    "scope",
    "key_digest",
    "window_started_at",
    "request_count",
    "created_at",
    "updated_at",
)


class PostgresLifecycleThrottleRepository(
    PostgresIdentityRepository, LifecycleThrottleRepository
):
    """Atomically reserve a persisted lifecycle request slot by digest."""

    def __init__(self, connection: DatabaseSession) -> None:
        super().__init__(connection)

    def reserve(
        self,
        scope: Literal["receipt_username", "receipt_email", "receipt_ip", "proof_ip"],
        key_digest: str,
        now: datetime,
        *,
        limit: int,
        window: timedelta,
    ) -> LifecycleThrottleReservation:
        """Increment or reset a fixed-window counter before identity lookup."""
        self._validate(scope, key_digest, now, limit, window)
        row = self._write(
            "INSERT INTO operational.lifecycle_throttle AS throttle "
            "(scope, key_digest, window_started_at, request_count, created_at, updated_at) "
            "VALUES (%s, %s, %s, 1, %s, %s) "
            "ON CONFLICT (scope, key_digest) DO UPDATE SET "
            "window_started_at = CASE "
            "WHEN throttle.window_started_at + %s "
            "<= EXCLUDED.window_started_at THEN EXCLUDED.window_started_at "
            "ELSE throttle.window_started_at END, "
            "request_count = CASE "
            "WHEN throttle.window_started_at + %s "
            "<= EXCLUDED.window_started_at THEN 1 "
            "ELSE throttle.request_count + 1 END, "
            "updated_at = EXCLUDED.updated_at "
            "RETURNING scope, key_digest, window_started_at, request_count, "
            "created_at, updated_at",
            (scope, key_digest, now, now, now, window, window),
        )
        persisted = LifecycleThrottleRow.model_validate(
            dict(zip(_RETURNED_FIELDS, row, strict=True))
        )
        if persisted.request_count <= limit:
            return LifecycleThrottleReservation(allowed=True, retry_after_seconds=0)

        seconds_left = (persisted.window_started_at + window - now).total_seconds()
        return LifecycleThrottleReservation(
            allowed=False,
            retry_after_seconds=max(1, ceil(seconds_left)),
        )

    @staticmethod
    def _validate(
        scope: str,
        key_digest: str,
        now: datetime,
        limit: int,
        window: timedelta,
    ) -> None:
        """Reject malformed inputs before opening a database cursor."""
        if not isinstance(scope, str) or scope not in _SCOPES:
            raise ValueError("invalid lifecycle throttle scope")
        if (
            not isinstance(key_digest, str)
            or _DIGEST_PATTERN.fullmatch(key_digest) is None
        ):
            raise ValueError("invalid lifecycle throttle key digest")
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ValueError("lifecycle throttle time must be timezone-aware")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= _POSTGRES_INTEGER_MAX
        ):
            raise ValueError("lifecycle throttle limit is out of bounds")
        if not isinstance(window, timedelta) or window <= timedelta(0):
            raise ValueError("lifecycle throttle window must be positive")
