"""SMTP-independent weekly digest message."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WeeklyDigestMessage:
    recipient: str = field(repr=False)
    subject: str
    body: str = field(repr=False)
    message_id: str
