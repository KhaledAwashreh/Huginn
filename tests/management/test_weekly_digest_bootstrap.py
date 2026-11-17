import pytest
from cryptography.fernet import Fernet

from huginn.management.config import ManagementConfig
from huginn.management.weekly_digest_bootstrap import create_weekly_digest_service


@pytest.mark.parametrize("enabled", [False, True])
def test_default_weekly_composition_is_inert_and_uses_the_shared_workflow(
    monkeypatch, enabled
):
    def unexpected_connection(*args, **kwargs):
        raise AssertionError("Composition must not open a database connection")

    monkeypatch.setattr(
        "huginn.management.weekly_digest_bootstrap.ManagementConnectionFactory",
        lambda _: unexpected_connection,
    )
    service = create_weekly_digest_service(
        ManagementConfig(
            "unused",
            simple_discovery_enabled=enabled,
            environment="test",
            web_origin="http://localhost:4173",
            smtp_sender="digest@example.test",
            lifecycle_proof_key=Fernet.generate_key().decode(),
        )
    )
    assert service._simple_discovery_enabled is enabled
    assert service._generation._simple_discovery_enabled is enabled
