"""Delivery boundary for composed weekly digests."""

from datetime import datetime
from typing import Protocol

from huginn.management.application.read_models.weekly_digest_message import (
    WeeklyDigestMessage,
)


class WeeklyDigestSender(Protocol):
    def send(self, message: WeeklyDigestMessage) -> datetime:
        """Return the acknowledged SMTP handoff time, including its timezone."""
        ...
