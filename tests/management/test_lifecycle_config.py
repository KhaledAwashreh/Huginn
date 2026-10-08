from dataclasses import replace

import pytest
from cryptography.fernet import Fernet

from huginn.management.config import ManagementConfig


def test_lifecycle_configuration_is_optional_for_api_only_startup():
    config = ManagementConfig("unused")
    assert hasattr(config, "lifecycle_proof_key"), (
        "lifecycle deployment settings are missing"
    )
    assert config.lifecycle_proof_key is None
    assert config.web_origin is None


def test_lifecycle_config_secrets_are_hidden_and_defaults_bounded():
    secret = Fernet.generate_key().decode()
    config = ManagementConfig(
        "unused",
        lifecycle_proof_key=secret,
        web_origin="http://localhost:4173",
        smtp_password="secret-mail-password",
    )
    assert secret not in repr(config)
    assert "secret-mail-password" not in repr(config)
    assert config.verification_ttl_seconds == 86400
    assert config.reset_ttl_seconds == 1800
    assert config.receipt_username_limit == 5
    assert config.receipt_email_limit == 5
    assert config.receipt_ip_limit == 20
    assert config.proof_ip_limit == 10
    for fields in (
        {"web_origin": "https://app.test/path"},
        {"web_origin": "https://user:secret@app.test"},
        {"web_origin": "javascript:foo"},
        {"verification_ttl_seconds": 0},
        {"reset_ttl_seconds": 999999999},
        {"smtp_port": 0},
        {"smtp_tls": "other"},
        {"receipt_username_limit": 0},
        {"receipt_email_limit": 0},
        {"lifecycle_proof_key": "invalid-secret"},
    ):
        with pytest.raises(ValueError):
            replace(config, **fields)
