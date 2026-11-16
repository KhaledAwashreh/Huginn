from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ConflictError
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.command_receipt import (
    PostgresCommandReceiptRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_command_receipt,
)


def test_command_receipt_uses_business_key_only_and_freezes_original_outcome(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        repository = PostgresCommandReceiptRepository(
            PsycopgDatabaseSession(connection)
        )
        resource_id = uuid4()
        receipt = valid_command_receipt(
            identity,
            resource_id=resource_id,
            resource_version=1,
            key="save-once",
            payload_fingerprint="f" * 64,
            result_snapshot={"id": str(resource_id), "stage": "saved", "version": 1},
        )

        assert repository.get_by_key(identity.business_id, "save-once") is None
        assert repository.record(receipt) == receipt
        assert repository.get_by_key(identity.business_id, "save-once") == receipt
        with pytest.raises(ConflictError):
            repository.record(replace(receipt, resource_version=2))
        assert repository.get_by_key(identity.business_id, "save-once") == receipt
        assert repository.get_by_key(uuid4(), "save-once") is None
