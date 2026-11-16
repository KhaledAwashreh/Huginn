from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.value_objects.command_identity import CommandIdentity


def test_receipt_replays_the_committed_result_snapshot_and_version():
    receipt = CommandReceipt(
        business_id=uuid4(),
        scope="prospect.save",
        identity=CommandIdentity("request-1", "a" * 64),
        resource_kind="prospect",
        resource_id=uuid4(),
        resource_version=1,
        result_snapshot={"stage": "saved", "origin_id": "origin-1"},
        recorded_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert receipt.result_snapshot.value["stage"] == "saved"
    assert receipt.resource_version == 1
