from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.policies.command_retry import validate_command_retry
from huginn.management.domain.value_objects.command_identity import CommandIdentity


def test_replay_returns_committed_result_only_for_same_key_scope_and_fingerprint():
    identity = CommandIdentity("request-1", "a" * 64)
    receipt = CommandReceipt(
        business_id=uuid4(),
        scope="prospect.save",
        identity=identity,
        resource_kind="prospect",
        resource_id=uuid4(),
        resource_version=1,
        result_snapshot={"stage": "saved"},
        recorded_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert validate_command_retry(receipt, "prospect.save", identity)
    with pytest.raises(ConflictError):
        validate_command_retry(receipt, "prospect.reject", identity)
    with pytest.raises(ConflictError):
        validate_command_retry(
            receipt, "prospect.save", CommandIdentity("request-1", "b" * 64)
        )
