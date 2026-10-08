"""Authenticated mail envelopes; lifecycle design section 4 and Fernet docs."""

import json
import re

from cryptography.fernet import Fernet, InvalidToken

from huginn.management.application.protocols.proof_cipher import ProofCipher
from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)


class EncryptedProofCipher(ProofCipher):
    def __init__(self, key: bytes | str) -> None:
        try:
            self._cipher = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid lifecycle encryption key") from exc

    def encrypt(self, message: LifecycleMailMessage) -> bytes:
        return self._cipher.encrypt(
            json.dumps(
                {
                    "recipient": message.recipient,
                    "purpose": message.purpose,
                    "token": message.token,
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )

    def decrypt(self, payload: bytes) -> LifecycleMailMessage:
        try:
            data = json.loads(self._cipher.decrypt(payload))
            if not isinstance(data, dict) or set(data) != {
                "recipient",
                "purpose",
                "token",
            }:
                raise ValueError
            if data["purpose"] not in {"verify_email", "reset_password"}:
                raise ValueError
            recipient, token = data["recipient"], data["token"]
            if (
                not isinstance(recipient, str)
                or not 3 <= len(recipient) <= 254
                or not re.fullmatch(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+", recipient)
            ):
                raise ValueError
            if not isinstance(token, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,1024}", token
            ):
                raise ValueError
            return LifecycleMailMessage(recipient, data["purpose"], token)
        except (InvalidToken, ValueError, TypeError, UnicodeError) as exc:
            raise ValueError("invalid encrypted lifecycle payload") from exc
