from dataclasses import replace
from uuid import uuid4

import psycopg

from huginn.management.application.services.signup_service import SignupService
from huginn.management.domain.services.identity_validation import (
    validated_identity_fields,
)
from huginn.management.presentation.api.requests.forgot_password import (
    ForgotPasswordRequest,
)
from tests.lifecycle_service_helpers import account, services, signup_request
from tests.postgres_harness import provisioned_postgres


def test_receipt_request_uses_normalized_email():
    assert (
        ForgotPasswordRequest(email=" Person@Example.test ").email
        == "person@example.test"
    )


def test_domain_normalizes_email():
    fields = validated_identity_fields(
        username="person",
        first_name="A",
        last_name="B",
        email=" Person@Example.test ",
        phone_number="+4455555555",
        country_of_residence="GB",
        timezone=None,
    )
    assert fields[3] == "person@example.test"


def test_duplicate_email_signup_does_not_create_account():
    with provisioned_postgres("huginn_unique_email") as url:
        build, _ = services(url)
        request = signup_request(email=f"{uuid4()}@example.test")
        first = build(SignupService).execute(request)
        other = replace(
            request,
            username=str(uuid4()),
            email=request.email.upper(),
            client_ip=str(uuid4()),
        )
        assert build(SignupService).execute(other) == first
        assert account(url, other.username) is None
        with psycopg.connect(url) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM operational.lifecycle_mail_outbox"
                ).fetchone()[0]
                == 1
            )


def test_concurrent_duplicate_email_signup_rolls_back_losing_account():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from huginn.management.persistence.repositories.account_recovery_identity import (
        PostgresAccountRecoveryIdentityRepository,
    )

    with provisioned_postgres("huginn_email_race") as url:
        barrier = Barrier(2)

        class RacingRecovery(PostgresAccountRecoveryIdentityRepository):
            def get_by_email(self, email):
                result = super().get_by_email(email)
                barrier.wait(timeout=10)
                return result

        build, _ = services(
            url, recovery_identities_factory=lambda uow: RacingRecovery(uow.connection)
        )
        request = signup_request()
        other = replace(
            request,
            username=str(uuid4()),
            email=request.email.upper(),
            client_ip=str(uuid4()),
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(
                pool.map(
                    lambda value: build(SignupService).execute(value), (request, other)
                )
            )
        assert receipts[0] == receipts[1]
        with psycopg.connect(url) as conn:
            for table in (
                "accounts",
                "users",
                "professional_profiles",
                "account_recovery_identity",
                "account_lifecycle_proofs",
                "lifecycle_mail_outbox",
            ):
                assert (
                    conn.execute(
                        f"SELECT count(*) FROM operational.{table}"
                    ).fetchone()[0]
                    == 1
                )


def test_direct_contact_and_pending_verified_email_uniqueness():
    import pytest

    with (
        provisioned_postgres("huginn_email_constraints") as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        first, second = uuid4(), uuid4()
        for identity in (first, second):
            conn.execute(
                "INSERT INTO operational.accounts (id,username,password_hash) VALUES (%s,%s,'hash')",
                (identity, str(identity)),
            )
            conn.execute(
                "INSERT INTO operational.users (account_id,first_name,last_name,email,phone_number,country_of_residence) VALUES (%s,'Ada','L',%s,'+12025550123','US')",
                (identity, f"{identity}@example.test"),
            )
        conn.execute(
            "UPDATE operational.users SET email='Owner@example.test' WHERE account_id=%s",
            (first,),
        )
        with pytest.raises(psycopg.errors.UniqueViolation) as error:
            conn.execute(
                "UPDATE operational.users SET email='owner@EXAMPLE.test',first_name='Changed' WHERE account_id=%s",
                (second,),
            )
        assert error.value.diag.constraint_name == "users_email_lower_key"
        assert (
            conn.execute(
                "SELECT first_name FROM operational.users WHERE account_id=%s",
                (second,),
            ).fetchone()[0]
            == "Ada"
        )
        conn.execute(
            "INSERT INTO operational.account_recovery_identity (account_id,verification_required,verified_email,verified_at) VALUES (%s,false,'Owner@example.test',now())",
            (first,),
        )
        with pytest.raises(psycopg.errors.UniqueViolation) as error:
            conn.execute(
                "INSERT INTO operational.account_recovery_identity (account_id,verification_required,pending_email) VALUES (%s,true,'owner@EXAMPLE.test')",
                (second,),
            )
        assert (
            error.value.diag.constraint_name
            == "account_recovery_identity_email_lower_key"
        )


def test_email_receipts_use_recovery_snapshot_after_contact_changes():
    from datetime import UTC, datetime, timedelta

    from huginn.management.application.requests.forgot_password_request import (
        ForgotPasswordRequest,
    )
    from huginn.management.application.requests.resend_verification_request import (
        ResendVerificationRequest,
    )
    from huginn.management.application.requests.verify_email_request import (
        VerifyEmailRequest,
    )
    from huginn.management.application.services.forgot_password_service import (
        ForgotPasswordService,
    )
    from huginn.management.application.services.resend_verification_service import (
        ResendVerificationService,
    )
    from huginn.management.application.services.verify_email_service import (
        VerifyEmailService,
    )
    from tests.lifecycle_service_helpers import queued

    with provisioned_postgres("huginn_email_snapshot") as url:
        now = [datetime.now(UTC)]
        build, cipher = services(url, clock=lambda: now[0])
        request = signup_request()
        build(SignupService).execute(request)
        account_id, user_id = account(url, request.username)
        changed = f"{uuid4()}@example.test"
        with psycopg.connect(url) as conn:
            conn.execute(
                "UPDATE operational.users SET email=%s WHERE id=%s", (changed, user_id)
            )
        now[0] += timedelta(seconds=61)
        build(ResendVerificationService).execute(
            ResendVerificationRequest(f" {request.email.upper()} ", str(uuid4()))
        )
        verification = queued(url, cipher, account_id, "verify_email")
        assert verification.recipient == request.email
        build(VerifyEmailService).execute(
            VerifyEmailRequest(verification.token, str(uuid4()))
        )
        receipt = build(ForgotPasswordService).execute(
            ForgotPasswordRequest(changed, str(uuid4()))
        )
        with psycopg.connect(url) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM operational.lifecycle_mail_outbox WHERE purpose='reset_password'"
                ).fetchone()[0]
                == 0
            )
        assert (
            build(ForgotPasswordService).execute(
                ForgotPasswordRequest(request.email.upper(), str(uuid4()))
            )
            == receipt
        )
        assert (
            queued(url, cipher, account_id, "reset_password").recipient == request.email
        )
        other = replace(request, username=str(uuid4()), client_ip=str(uuid4()))
        assert build(SignupService).execute(other).message == receipt.message
        assert account(url, other.username) is None


def test_public_duplicate_email_and_contact_conflict_are_safe(management_database_url):
    from fastapi.testclient import TestClient

    from huginn.management.app import create_app
    from tests.management.test_lifecycle_api import _message, _settings, _signup

    config = _settings(management_database_url)
    first, second = str(uuid4()), str(uuid4())
    first_body, second_body = _signup(first), _signup(second)
    with TestClient(create_app(config)) as client:
        receipt = client.post("/api/v1/accounts", json=first_body)
        assert receipt.status_code == 202
        duplicate = client.post(
            "/api/v1/accounts",
            json=second_body | {"email": f" {first_body['email'].upper()} "},
        )
        assert duplicate.status_code == 202 and duplicate.json() == receipt.json()
        assert account(management_database_url, second) is None
        assert client.post("/api/v1/accounts", json=second_body).status_code == 202
        token = _message(config, first, "verify_email").token
        assert (
            client.post(
                "/api/v1/email-verifications", json={"token": token}
            ).status_code
            == 204
        )
        login = client.post(
            "/api/v1/sessions",
            json={"username": first, "password": first_body["password"]},
        )
        conflict = client.patch(
            "/api/v1/me",
            json={"email": second_body["email"].upper(), "first_name": "Overwrite"},
            headers={"X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert conflict.status_code == 409
        assert second_body["email"] not in conflict.text and second not in conflict.text
        user = client.get("/api/v1/me").json()
        assert user["email"] == first_body["email"] and user["first_name"] == "Ada"
        for path in ("/api/v1/password-resets", "/api/v1/email-verifications/resend"):
            assert client.post(path, json={"username": first}).status_code == 422
            assert client.post(path, json={"email": "invalid"}).status_code == 422


def test_trusted_unverified_contact_is_not_forgot_destination(management_database_url):
    from fastapi.testclient import TestClient

    from huginn.management.app import create_account_administration_services, create_app
    from huginn.management.application.commands.provisioning import ProvisionIdentity
    from tests.management.test_lifecycle_api import _settings, _signup

    config = _settings(management_database_url)
    username = str(uuid4())
    email = f"{username}@example.test"
    create_account_administration_services(config).provisioning.provision(
        ProvisionIdentity(
            username, "Ada", "L", email, "+12025550123", "US", None, "SignUp!12345"
        )
    )
    with TestClient(create_app(config)) as client:
        unknown = client.post(
            "/api/v1/password-resets", json={"email": f"{uuid4()}@example.test"}
        )
        known = client.post("/api/v1/password-resets", json={"email": email.upper()})
        assert (
            unknown.status_code == known.status_code == 202
            and known.json() == unknown.json()
        )
        other = str(uuid4())
        assert (
            client.post(
                "/api/v1/accounts", json=_signup(other) | {"email": email.upper()}
            ).status_code
            == 202
        )
        assert account(management_database_url, other) is None
    with psycopg.connect(management_database_url) as conn:
        account_id = account(management_database_url, username)[0]
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.lifecycle_mail_outbox WHERE account_id=%s",
                (account_id,),
            ).fetchone()[0]
            == 0
        )
