from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.suppression_block import (
    PostgresSuppressionBlockRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
)


def test_suppression_history_boundary_and_versioned_clear_are_owner_scoped(
    management_database_url,
):
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        other = seed_prospecting_owner_company(connection)
        repository = PostgresSuppressionBlockRepository(
            PsycopgDatabaseSession(connection)
        )
        cooldown = SuppressionBlock(
            id=uuid4(),
            business_id=identity.business_id,
            company_id=identity.company_id,
            kind=SuppressionKind("cooldown"),
            created_at=now,
            effective_at=now,
            expires_at=now + timedelta(days=1),
        )
        rejection = SuppressionBlock(
            id=uuid4(),
            business_id=identity.business_id,
            company_id=identity.company_id,
            kind=SuppressionKind("rejection"),
            created_at=now,
            effective_at=now,
            created_by_user_id=identity.owner_user_id,
            reason="Not a fit",
        )
        other_business_block = SuppressionBlock(
            id=uuid4(),
            business_id=other.business_id,
            company_id=identity.company_id,
            kind=SuppressionKind("pause"),
            created_at=now,
            effective_at=now,
            created_by_user_id=other.owner_user_id,
            reason="Different owner",
        )
        repository.append(cooldown)
        repository.append(rejection)
        repository.append(other_business_block)
        expected_owner_blocks = tuple(
            sorted((cooldown, rejection), key=lambda block: block.id.int)
        )

        assert (
            repository.list_active(identity.business_id, identity.company_id, now)
            == expected_owner_blocks
        )
        assert (
            repository.list_active(
                identity.business_id, identity.company_id, now - timedelta(seconds=1)
            )
            == ()
        )
        assert repository.list_active(
            identity.business_id, identity.company_id, now + timedelta(days=1)
        ) == (rejection,)
        assert (
            repository.list_history(identity.business_id, identity.company_id)
            == expected_owner_blocks
        )
        assert repository.list_history(other.business_id, identity.company_id) == (
            other_business_block,
        )

        cleared = repository.clear_one(
            identity.business_id,
            identity.company_id,
            cooldown.id,
            cooldown.version,
            identity.owner_user_id,
            now + timedelta(hours=1),
        )
        assert cleared == SuppressionBlock(
            **{
                **cooldown.__dict__,
                "cleared_at": now + timedelta(hours=1),
                "cleared_by_user_id": identity.owner_user_id,
                "version": cooldown.version + 1,
            }
        )
        assert repository.list_active(
            identity.business_id, identity.company_id, now
        ) == (rejection,)
        with pytest.raises(ConflictError):
            repository.clear_one(
                identity.business_id,
                identity.company_id,
                cooldown.id,
                cooldown.version,
                identity.owner_user_id,
                now + timedelta(hours=2),
            )
        with pytest.raises(ConflictError):
            repository.clear_one(
                identity.business_id,
                identity.company_id,
                other_business_block.id,
                other_business_block.version,
                identity.owner_user_id,
                now + timedelta(hours=2),
            )
        assert connection.execute(
            "SELECT version,cleared_at,cleared_by_user_id "
            "FROM operational.suppression_blocks WHERE id=%s",
            (cooldown.id,),
        ).fetchone() == (
            cooldown.version + 1,
            now + timedelta(hours=1),
            identity.owner_user_id,
        )


def test_owner_scoped_get_by_block_id_cannot_discover_another_business_row(
    management_database_url,
):
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        other = seed_prospecting_owner_company(connection)
        repository = PostgresSuppressionBlockRepository(
            PsycopgDatabaseSession(connection)
        )
        block = SuppressionBlock(
            id=uuid4(),
            business_id=identity.business_id,
            company_id=identity.company_id,
            kind=SuppressionKind("rejection"),
            created_at=now,
            created_by_user_id=identity.owner_user_id,
            reason="Explicitly not relevant",
        )
        repository.append(block)

        assert repository.get_owned(identity.business_id, block.id) == block
        assert repository.get_owned(other.business_id, block.id) is None
        assert repository.get_owned(identity.business_id, uuid4()) is None
