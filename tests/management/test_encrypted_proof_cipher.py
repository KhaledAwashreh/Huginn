import importlib
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)


def _cipher(key):
    path = (
        Path(__file__).parents[2]
        / "src/huginn/management/security/encrypted_proof_cipher.py"
    )
    assert path.exists(), "authenticated lifecycle envelope is missing"
    return importlib.import_module(
        "huginn.management.security.encrypted_proof_cipher"
    ).EncryptedProofCipher(key)


def test_encrypted_envelope_roundtrip_hides_proof_and_address():
    key = Fernet.generate_key()
    cipher = _cipher(key)
    message = LifecycleMailMessage(
        "private@example.test", "verify_email", "private-proof"
    )
    encrypted = cipher.encrypt(message)
    assert message.recipient.encode() not in encrypted
    assert message.token.encode() not in encrypted
    assert cipher.decrypt(encrypted) == message
    assert cipher.encrypt(message) != encrypted
    assert key.decode() not in repr(cipher)


def test_modified_ciphertext_and_wrong_key_fail_with_safe_error():
    cipher = _cipher(Fernet.generate_key())
    payload = cipher.encrypt(
        LifecycleMailMessage("private@example.test", "reset_password", "private-proof")
    )
    for decryptor, candidate in (
        (cipher, payload[:-3] + b"XXX"),
        (_cipher(Fernet.generate_key()), payload),
    ):
        with pytest.raises(
            ValueError, match="invalid encrypted lifecycle payload"
        ) as error:
            decryptor.decrypt(candidate)
        assert "private" not in str(error.value)


def test_authenticated_but_invalid_payload_is_rejected():
    key = Fernet.generate_key()
    cipher = _cipher(key)
    for plaintext in (
        b"not json",
        b'{"recipient":"private@example.test","purpose":"other","token":"secret"}',
        b'{"recipient":"private@example.test","purpose":"verify_email","token":"secret","extra":true}',
    ):
        with pytest.raises(ValueError, match="invalid encrypted lifecycle payload"):
            cipher.decrypt(Fernet(key).encrypt(plaintext))
