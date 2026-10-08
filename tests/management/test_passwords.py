import json
import logging

import pytest
from werkzeug.security import check_password_hash

from huginn.management.security.passwords import (
    Password,
    hash_password,
    verify_password,
)


@pytest.mark.parametrize("length", [8, 1024])
def test_password_accepts_inclusive_length_boundaries(length):
    assert len(Password("p" * length).value) == length


@pytest.mark.parametrize("length", [7, 1025])
def test_password_rejects_values_outside_length_boundaries(length):
    with pytest.raises(ValueError):
        Password("p" * length)


def test_password_is_preserved_verbatim_without_trimming_or_normalization():
    value = "  aBc! 123456  "

    assert Password(value).value == value


def test_password_hashing_uses_distinct_salted_werkzeug_scrypt_hashes():
    password = Password("correct horse battery staple")

    first = hash_password(password)
    second = hash_password(password)

    assert first != second
    assert first.startswith("scrypt:")
    assert check_password_hash(first, password.value)


def test_password_hash_verification_accepts_correct_and_rejects_wrong_value():
    encoded = hash_password(Password("correct horse battery staple"))

    assert verify_password(Password("correct horse battery staple"), encoded)
    assert not verify_password(Password("wrong password value"), encoded)


def test_password_is_not_exposed_in_repr_or_logs(caplog):
    secret = "not-for-logs-password-value"
    password = Password(secret)

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("huginn.management.security.passwords").debug(
            "received password"
        )

    assert secret not in repr(password)
    assert secret not in caplog.text
    assert secret not in repr(hash_password(password))


def test_password_cannot_be_serialized_into_a_response_value():
    password = Password("response-secret-password")

    with pytest.raises(TypeError):
        json.dumps({"credential": password})


@pytest.mark.parametrize(
    "value",
    ["Pass123!", "Password1234567!", "A1!abcde", "Abcdefghijklm1!😀", "Abcdef1! "],
)
def test_new_password_accepts_user_requested_composition(value):
    from huginn.management.security.passwords import validate_new_password

    assert validate_new_password(value).value == value


@pytest.mark.parametrize(
    "value",
    [
        "Aa1!abc",
        "Password12345678!",
        "Password!",
        "Password123",
        "1234567!",
        "Pass123 ",
    ],
)
def test_new_password_rejects_length_or_missing_composition(value):
    from huginn.management.security.passwords import validate_new_password

    with pytest.raises(ValueError):
        validate_new_password(value)
