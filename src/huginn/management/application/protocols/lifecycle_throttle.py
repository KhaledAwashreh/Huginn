"""Persisted public admission boundary, independent of account lookup."""

from datetime import datetime, timedelta
from typing import Literal, Protocol

from huginn.management.application.read_models.lifecycle_throttle import (
    LifecycleThrottleReservation,
)


class LifecycleThrottleRepository(Protocol):
    def reserve(
        self,
        scope: Literal["receipt_username", "receipt_email", "receipt_ip", "proof_ip"],
        key_digest: str,
        now: datetime,
        *,
        limit: int,
        window: timedelta,
    ) -> LifecycleThrottleReservation: ...
