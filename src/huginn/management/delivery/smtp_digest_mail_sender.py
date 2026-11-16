"""Plain-text weekly digests over the shared bounded SMTP transport."""

from datetime import datetime
from email.message import EmailMessage

from huginn.management.application.errors.mail_pre_transport import (
    MailPreTransportError,
)
from huginn.management.application.protocols.weekly_digest_sender import (
    WeeklyDigestSender,
)
from huginn.management.application.read_models.weekly_digest_message import (
    WeeklyDigestMessage,
)
from huginn.management.config import ManagementConfig
from huginn.management.delivery.smtp_transport import send_email, validate_credentials


class SmtpDigestMailSender(WeeklyDigestSender):
    def __init__(self, config: ManagementConfig) -> None:
        validate_credentials(config)
        self._config = config

    def send(self, message: WeeklyDigestMessage) -> datetime:
        try:
            email = _render_digest(self._config, message)
        except TypeError, ValueError:
            raise MailPreTransportError("Invalid digest mail message") from None
        return send_email(
            self._config, email, error_message="digest mail transport failed"
        )


def _render_digest(
    config: ManagementConfig, message: WeeklyDigestMessage
) -> EmailMessage:
    if any(ord(char) < 32 or ord(char) == 127 for char in message.recipient):
        raise ValueError("invalid digest mail recipient")
    email = EmailMessage()
    email["To"] = message.recipient
    email["From"] = config.smtp_sender
    email["Subject"] = message.subject
    email["Message-ID"] = message.message_id
    for header in ("To", "From"):
        addresses = email[header].addresses
        if len(addresses) != 1 or not addresses[0].username or not addresses[0].domain:
            raise ValueError("invalid digest mail address")
    email.set_content(message.body)
    return email
