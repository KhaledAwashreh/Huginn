"""SMTP-independent lifecycle mail delivery boundary."""

from typing import Protocol

from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)


class LifecycleMailSender(Protocol):
    def send(self, message: LifecycleMailMessage) -> None: ...
