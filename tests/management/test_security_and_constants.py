import hashlib
import re

import pytest

from huginn.management.constants.authentication import (
    PASSWORD_HASH_METHOD,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
)
from huginn.management.constants.database import MANAGEMENT_SCHEMA
from huginn.management.constants.http import SENSITIVE_FIELDS
from huginn.management.constants.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    POSTGRES_BIGINT_MAX,
)
from huginn.management.constants.targeting import ICP_DIMENSION_FIELDS
from huginn.management.security.passwords import (
    Password,
    hash_password,
    needs_rehash,
    verify_password,
)
from huginn.management.security.tokens import digest_token, generate_token


def test_constants_are_grouped_by_semantic_owner():
    assert (PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH) == (12, 1024)
    assert PASSWORD_HASH_METHOD == "scrypt"
    assert MANAGEMENT_SCHEMA == "operational"
    assert {"password", "password_hash", "token_digest"} <= SENSITIVE_FIELDS
    assert (DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, POSTGRES_BIGINT_MAX) == (
        50,
        100,
        2**63 - 1,
    )
    assert ICP_DIMENSION_FIELDS == (
        "industries",
        "company_sizes",
        "geographies",
        "exclusions",
    )


def test_password_validation_and_redaction():
    assert Password("p" * PASSWORD_MIN_LENGTH).value == "p" * 12
    assert Password("p" * PASSWORD_MAX_LENGTH).value == "p" * 1024
    with pytest.raises(ValueError):
        Password("p" * (PASSWORD_MIN_LENGTH - 1))
    with pytest.raises(ValueError):
        Password("p" * (PASSWORD_MAX_LENGTH + 1))
    value = "  unchanged password  "
    assert Password(value).value == value
    assert repr(Password(value)) == "Password(<redacted>)"


def test_password_security_helpers_hash_verify_and_detect_upgrade():
    secret = Password("correct horse battery staple")
    encoded = hash_password(secret)

    assert encoded.startswith(f"{PASSWORD_HASH_METHOD}:")
    assert verify_password(secret, encoded)
    assert not verify_password(Password("incorrect horse battery staple"), encoded)
    assert not needs_rehash(encoded, encoded.partition("$")[0])
    assert needs_rehash("pbkdf2:sha256:600000$salt$hash", "scrypt:32768:8:1")


def test_token_helpers_generate_opaque_values_and_only_digest_persisted_values():
    token = generate_token()

    assert isinstance(token, str)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    assert len(token) == 43
    assert digest_token(token) == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert token not in digest_token(token)
