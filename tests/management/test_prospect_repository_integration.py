from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.prospect import (
    PostgresProspectRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_prospect,
)


def test_prospect_create_and_update_enforce_business_company_and_expected_version(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        repository = PostgresProspectRepository(PsycopgDatabaseSession(connection))
        prospect = valid_prospect(identity)

        created = repository.create(prospect)
        assert created == prospect
        assert repository.get_owned(identity.business_id, prospect.id) == prospect
        assert (
            repository.get_by_business_company(
                identity.business_id, identity.company_id
            )
            == prospect
        )
        assert repository.get_owned(uuid4(), prospect.id) is None
        assert repository.create(valid_prospect(identity)) == prospect

        updated = repository.update_owned(
            identity.business_id,
            prospect.id,
            prospect.version,
            replace(
                prospect,
                stage=ProspectStage("contacted"),
                updated_at=datetime.now(UTC) + timedelta(seconds=1),
                version=prospect.version + 1,
                notes="Sent the first message",
            ),
        )
        assert updated.stage.value == "contacted"
        assert updated.version == 2
        assert updated.notes == "Sent the first message"
        with pytest.raises(ConflictError):
            repository.update_owned(
                identity.business_id,
                prospect.id,
                prospect.version,
                replace(updated, version=updated.version + 1),
            )
        with pytest.raises(NotFoundError):
            repository.update_owned(
                uuid4(), prospect.id, updated.version, replace(updated, version=3)
            )


def test_prospect_create_serializes_same_business_company_on_separate_connections(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        connection.commit()
    barrier = Barrier(2)

    def create_prospect():
        with psycopg.connect(management_database_url) as connection:
            barrier.wait()
            repository = PostgresProspectRepository(PsycopgDatabaseSession(connection))
            return repository.create(valid_prospect(identity))

    with ThreadPoolExecutor(max_workers=2) as workers:
        first, second = workers.map(lambda _: create_prospect(), range(2))
    assert first == second
    with psycopg.connect(management_database_url) as connection:
        persisted = PostgresProspectRepository(
            PsycopgDatabaseSession(connection)
        ).get_by_business_company(identity.business_id, identity.company_id)
    assert persisted == first
