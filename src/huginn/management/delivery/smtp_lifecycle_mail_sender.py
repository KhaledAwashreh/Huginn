"""Bounded SMTP adapter for account lifecycle messages."""

from email.message import EmailMessage

from huginn.management.application.constants.lifecycle_policy import (
    MAIL_TIMEOUT_SECONDS,
)
from huginn.management.application.protocols.lifecycle_mail_sender import (
    LifecycleMailSender,
)
from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)
from huginn.management.config import ManagementConfig
from huginn.management.delivery.smtp_transport import send_email, validate_credentials
from huginn.management.delivery.templates.reset_password import render_reset_mail
from huginn.management.delivery.templates.verify_email import render_verification_mail


def _render(config: ManagementConfig, message: LifecycleMailMessage) -> EmailMessage:
    if not config.web_origin:
        raise ValueError("trusted web origin is required for lifecycle mail")
    if message.purpose == "verify_email":
        renderer = render_verification_mail
    elif message.purpose == "reset_password":
        renderer = render_reset_mail
    else:
        raise ValueError("invalid lifecycle mail purpose")
    return renderer(
        recipient=message.recipient,
        sender=config.smtp_sender,
        token=message.token,
        web_origin=config.web_origin,
    )


class SmtpLifecycleMailSender(LifecycleMailSender):
    """Bound SMTP plus sender-process cleanup to one total 30-second budget."""

    def __init__(self, config: ManagementConfig) -> None:
        if not config.web_origin:
            raise ValueError("trusted web origin is required for lifecycle mail")
        validate_credentials(config)
        self._config = config

    def send(self, message: LifecycleMailMessage) -> None:
        send_email(
            self._config,
            _render(self._config, message),
            timeout_seconds=MAIL_TIMEOUT_SECONDS,
            error_message="lifecycle mail transport failed",
        )
