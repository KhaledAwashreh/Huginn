from dataclasses import replace
from uuid import uuid4

import psycopg
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from huginn.management.app import create_account_administration_services, create_app
from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.config import ManagementConfig
from huginn.management.security.encrypted_proof_cipher import EncryptedProofCipher


def _settings(database_url):
    return ManagementConfig(
        database_url,
        environment="test",
        lifecycle_proof_key=Fernet.generate_key().decode(),
        web_origin="http://testserver",
    )


def _signup(username):
    return {
        "username": username,
        "password": "SignUp!12345",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": f"{username.lower()}@example.test",
        "phone_number": "+12025550123",
        "country_of_residence": "US",
    }


def _message(config, username, purpose):
    with psycopg.connect(config.database_url) as connection:
        payload = connection.execute(
            "SELECT o.encrypted_payload FROM operational.lifecycle_mail_outbox o JOIN operational.accounts a ON a.id=o.account_id WHERE lower(a.username)=lower(%s) AND o.purpose=%s ORDER BY o.created_at DESC LIMIT 1",
            (username, purpose),
        ).fetchone()[0]
    return EncryptedProofCipher(config.lifecycle_proof_key).decrypt(bytes(payload))


def test_public_signup_verification_login_contact_change_and_reset(
    management_database_url,
):
    config = _settings(management_database_url)
    username = f"Public-{uuid4()}"
    with TestClient(create_app(config)) as client:
        assert (
            client.post("/api/v1/accounts", json=_signup(username)).status_code == 202
        )
        assert (
            client.post(
                "/api/v1/sessions",
                json={"username": username, "password": "SignUp!12345"},
            ).status_code
            == 401
        )
        message = _message(config, username, "verify_email")
        assert (
            client.get(
                "/api/v1/email-verifications", params={"token": message.token}
            ).status_code
            == 405
        )
        assert (
            client.post(
                "/api/v1/email-verifications", json={"token": message.token}
            ).status_code
            == 204
        )
        login = client.post(
            "/api/v1/sessions",
            json={"username": username, "password": "SignUp!12345"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        security = client.get("/api/v1/me/account-security")
        assert security.status_code == 200
        assert security.json()["recovery_email"] == _signup(username)["email"]
        assert security.headers["cache-control"] == "no-store"
        assert (
            client.patch(
                "/api/v1/me",
                json={"email": "changed@example.test"},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/password-resets", json={"email": _signup(username)["email"]}
            ).status_code
            == 202
        )
        reset = _message(config, username, "reset_password")
        assert reset.recipient == _signup(username)["email"]
        assert (
            client.post(
                "/api/v1/password-resets/complete",
                json={
                    "token": reset.token,
                    "new_password": "ResetNow!12345",
                },
            ).status_code
            == 204
        )
        assert client.get("/api/v1/sessions/current").status_code == 401
        assert (
            client.post(
                "/api/v1/password-resets/complete",
                json={"token": reset.token, "new_password": "OtherNow!12345"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/sessions",
                json={"username": username, "password": "ResetNow!12345"},
            ).status_code
            == 200
        )


def test_lifecycle_receipts_validation_origin_and_proof_errors_are_safe(
    management_database_url, caplog
):
    config = _settings(management_database_url)
    username = f"Receipt-{uuid4()}"
    with TestClient(create_app(config)) as client:
        first = client.post("/api/v1/accounts", json=_signup(username))
        assert first.status_code == 202
        assert (
            client.post("/api/v1/accounts", json=_signup(username)).json()
            == first.json()
        )
        assert (
            client.post(
                "/api/v1/password-resets",
                json={"email": f"unknown-{uuid4()}@example.test"},
            ).json()
            == first.json()
        )
        rejected = client.post(
            "/api/v1/accounts",
            json=_signup(f"Reject-{uuid4()}") | {"role": "secret-role-override"},
        )
        assert rejected.status_code == 422
        assert "secret-role-override" not in rejected.text
        assert (
            client.post(
                "/api/v1/accounts",
                json=_signup(f"Cross-{uuid4()}"),
                headers={"Origin": "https://elsewhere.test"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/email-verifications", json={"token": "private-bad-proof"}
            ).status_code
            == 422
        )
    assert "private-bad-proof" not in caplog.text
    assert "original@example.test" not in caplog.text


def test_missing_lifecycle_deployment_settings_are_safe_and_api_still_starts(
    management_database_url,
):
    with TestClient(create_app(ManagementConfig(management_database_url))) as client:
        assert client.get("/health").status_code == 200
        response = client.post(
            "/api/v1/accounts", json=_signup(f"Unconfigured-{uuid4()}")
        )
        assert response.status_code == 503
        assert "key" not in response.text.lower()
        assert response.json()["error"]["code"] == "service_unavailable"


def test_public_lifecycle_openapi_has_no_session_or_csrf_requirement():
    document = create_app(ManagementConfig("unused")).openapi()
    for path in (
        "/api/v1/accounts",
        "/api/v1/email-verifications",
        "/api/v1/email-verifications/resend",
        "/api/v1/password-resets",
        "/api/v1/password-resets/complete",
    ):
        assert not document["paths"][path]["post"].get("security")


def test_public_limits_are_persisted_generic_and_return_retry_after(
    management_database_url,
):
    config = replace(_settings(management_database_url), receipt_email_limit=2)
    username = f"Limited-{uuid4()}"
    with TestClient(create_app(config)) as client:
        assert (
            client.post("/api/v1/accounts", json=_signup(username)).status_code == 202
        )
        assert (
            client.post(
                "/api/v1/password-resets", json={"email": _signup(username)["email"]}
            ).status_code
            == 202
        )
        known = client.post(
            "/api/v1/password-resets", json={"email": _signup(username)["email"]}
        )
        assert known.status_code == 429
        assert int(known.headers["retry-after"]) >= 1
    with TestClient(create_app(config)) as other:
        assert (
            other.post(
                "/api/v1/email-verifications/resend",
                json={"email": _signup(username)["email"]},
            ).status_code
            == 429
        )
        absent = f"absent-{uuid4()}@example.test"
        for _ in range(2):
            assert (
                other.post(
                    "/api/v1/password-resets", json={"email": absent}
                ).status_code
                == 202
            )
        unknown = other.post("/api/v1/password-resets", json={"email": absent})
        assert unknown.status_code == 429
        assert unknown.json() == known.json()


def test_authenticated_initial_enrollment_is_csrf_protected_and_snapshot_bound(
    management_database_url,
):
    config = _settings(management_database_url)
    username = f"Trusted-{uuid4()}"
    create_account_administration_services(config).provisioning.provision(
        ProvisionIdentity(
            username,
            "Ada",
            "Lovelace",
            "trusted-original@example.test",
            "+12025550123",
            "US",
            None,
            "SignUp!12345",
        )
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/api/v1/me/account-security").status_code == 401
        login = client.post(
            "/api/v1/sessions",
            json={"username": username, "password": "SignUp!12345"},
        )
        assert login.status_code == 200
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert (
            client.post("/api/v1/me/recovery-email-verifications", json={}).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/me/recovery-email-verifications",
                json={"email": "replacement@example.test"},
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/me/recovery-email-verifications", json={}, headers=headers
            ).status_code
            == 202
        )
        message = _message(config, username, "verify_email")
        assert (
            client.patch(
                "/api/v1/me",
                json={"email": "trusted-changed@example.test"},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/email-verifications", json={"token": message.token}
            ).status_code
            == 204
        )
        assert (
            client.get("/api/v1/me/account-security").json()["recovery_email"]
            == "trusted-original@example.test"
        )
        assert (
            client.post(
                "/api/v1/me/recovery-email-verifications", json={}, headers=headers
            ).status_code
            == 409
        )
