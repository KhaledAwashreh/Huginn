import pytest

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)


def test_fingerprint_is_canonical_and_binds_command_type_and_payload():
    first = fingerprint_command_payload(
        "prospect.save", {"revision": "r1", "reason": "user"}
    )
    reordered = fingerprint_command_payload(
        "prospect.save", {"reason": "user", "revision": "r1"}
    )
    changed = fingerprint_command_payload(
        "prospect.save", {"reason": "other", "revision": "r1"}
    )
    other_type = fingerprint_command_payload(
        "prospect.reject", {"reason": "user", "revision": "r1"}
    )
    assert first == reordered
    assert first != changed
    assert first != other_type
    assert len(first) == 64


def test_fingerprint_rejects_non_json_and_non_finite_values():
    with pytest.raises(ValidationDomainError):
        fingerprint_command_payload("prospect.save", {"value": object()})
    with pytest.raises(ValidationDomainError):
        fingerprint_command_payload("prospect.save", {"value": float("nan")})
    with pytest.raises(ValidationDomainError):
        fingerprint_command_payload("prospect.save", {1: "ambiguous key"})
