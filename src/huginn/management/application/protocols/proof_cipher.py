"""Authenticated encrypted lifecycle mail envelope boundary."""

from typing import Protocol

from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)


class ProofCipher(Protocol):
    def encrypt(self, message: LifecycleMailMessage) -> bytes: ...
    def decrypt(self, payload: bytes) -> LifecycleMailMessage: ...
