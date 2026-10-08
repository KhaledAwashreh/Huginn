import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2] / "src/huginn/management/application"


def test_signup_values_hide_passwords_and_have_safe_generic_receipt():
    assert (ROOT / "requests/signup_request.py").exists(), "signup request is missing"
    request_type = importlib.import_module(
        "huginn.management.application.requests.signup_request"
    ).SignupRequest
    response_type = importlib.import_module(
        "huginn.management.application.responses.signup_response"
    ).SignupResponse
    request = request_type(
        username="Ada",
        password="private-password",
        first_name="Ada",
        last_name="Lovelace",
        email="private@example.test",
        phone_number="+12025550123",
        country_of_residence="US",
        client_ip="192.0.2.1",
    )
    assert "private-password" not in repr(request)
    with pytest.raises(FrozenInstanceError):
        request.username = "other"
    assert response_type().message == "Check your email for next steps"


def test_proof_requests_hide_secrets_from_repr():
    for name, kwargs in (
        ("verify_email", {"token": "secret-proof", "client_ip": "192.0.2.1"}),
        (
            "reset_password",
            {
                "token": "secret-proof",
                "new_password": "secret-password",
                "client_ip": "192.0.2.1",
            },
        ),
    ):
        assert (ROOT / f"requests/{name}_request.py").exists(), (
            f"missing {name} request"
        )
        module = importlib.import_module(
            f"huginn.management.application.requests.{name}_request"
        )
        value = getattr(
            module, "".join(part.title() for part in name.split("_")) + "Request"
        )(**kwargs)
        assert "secret-proof" not in repr(value)
        assert "secret-password" not in repr(value)
