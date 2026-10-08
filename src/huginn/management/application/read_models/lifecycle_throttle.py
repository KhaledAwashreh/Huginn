"""Admission result returned by persisted lifecycle throttling."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LifecycleThrottleReservation:
    allowed: bool
    retry_after_seconds: int
