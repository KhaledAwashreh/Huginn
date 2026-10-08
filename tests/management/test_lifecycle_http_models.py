import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).parents[2] / "src/huginn/management/presentation/api/requests"


def test_public_signup_uses_strict_identity_fields_and_rejects_privileged_overrides():
    assert (ROOT / "signup.py").exists(), "public signup HTTP contract is missing"
    SignupRequest = importlib.import_module(
        "huginn.management.presentation.api.requests.signup"
    ).SignupRequest
    values = {
        "username": " Ada ",
        "password": "SignUp!12345",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.test",
        "phone_number": "+12025550123",
        "country_of_residence": "US",
    }
    assert SignupRequest(**values).username == "Ada"
    assert "SignUp!12345" not in repr(SignupRequest(**values))
    for key in ("role", "status", "account_id", "user_id", "extra"):
        with pytest.raises(ValidationError):
            SignupRequest(**values, **{key: "admin"})
    for fields in (
        {"email": "bad"},
        {"phone_number": "123"},
        {"timezone": "Mars/Olympus"},
        {"password": "short"},
        {"username": 123},
        {"country_of_residence": "ZZ"},
        {"country_of_residence": "GB"},
        {"phone_number": "+120"},
        {"password": "NoDigits!"},
        {"password": "NoSymbols123"},
        {"password": "1234567!"},
        {"password": "TooLongPassword12!"},
    ):
        with pytest.raises(ValidationError):
            SignupRequest(**(values | fields))


def test_public_password_reset_enforces_same_composition_as_signup():
    from huginn.management.presentation.api.requests.reset_password import (
        ResetPasswordRequest,
    )

    assert (
        ResetPasswordRequest(token="proof", new_password="Pass123!").new_password
        == "Pass123!"
    )
    for value in (
        "short",
        "NoDigits!",
        "NoSymbols123",
        "1234567!",
        "TooLongPassword12!",
    ):
        with pytest.raises(ValidationError):
            ResetPasswordRequest(token="proof", new_password=value)


def test_lifecycle_tokens_are_hidden_and_enrollment_accepts_only_empty_json():
    assert (ROOT / "verify_email.py").exists(), "proof HTTP contract is missing"
    VerifyEmailRequest = importlib.import_module(
        "huginn.management.presentation.api.requests.verify_email"
    ).VerifyEmailRequest
    assert "private-proof" not in repr(VerifyEmailRequest(token="private-proof"))
    EnrollRecoveryEmailRequest = importlib.import_module(
        "huginn.management.presentation.api.requests.enroll_recovery_email"
    ).EnrollRecoveryEmailRequest
    assert EnrollRecoveryEmailRequest().model_dump() == {}
    with pytest.raises(ValidationError):
        EnrollRecoveryEmailRequest(email="other@example.test")
