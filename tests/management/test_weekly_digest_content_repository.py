from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.entities.offer_cycle import OfferCycle
from huginn.management.domain.entities.weekly_digest_content import WeeklyDigestContent
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.domain.value_objects.weekly_digest_member import (
    WeeklyDigestMember,
)
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.offer_cycle import (
    PostgresOfferCycleRepository,
)
from huginn.management.persistence.repositories.weekly_digest_content import (
    PostgresWeeklyDigestContentRepository,
)
from huginn.management.persistence.repositories.weekly_digest_delivery import (
    PostgresWeeklyDigestDeliveryRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
    seed_prospecting_owner_company,
)
from tests.postgres_harness import provisioned_postgres

_CONTENT_SCHEMA = Path("db/schema/operational-weekly-digest-content.sql")
_LEGACY_RECOMMENDATIONS_SCHEMA = Path("db/schema/operational-recommendations.sql")
_WEEKLY_SCHEMA = Path("db/schema/operational-weekly-digest.sql")
NOW = datetime(2051, 1, 2, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def weekly_digest_content_database_url():
    with provisioned_postgres("huginn_weekly_content_repository_test") as url:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(_LEGACY_RECOMMENDATIONS_SCHEMA.read_text())
            connection.execute(_WEEKLY_SCHEMA.read_text())
            connection.execute(_CONTENT_SCHEMA.read_text())
        yield url


def _setup(connection):
    identity, recommendation, revision = seed_owned_recommendation_revision(connection)
    session = PsycopgDatabaseSession(connection)
    cycle = OfferCycle(
        uuid4(),
        identity.business_id,
        identity.company_id,
        recommendation.id,
        revision.id,
        f"content-cycle-{uuid4()}",
        "c" * 64,
        OfferCycleStatus("preparing"),
        NOW,
        NOW,
        "claim-token",
        NOW + timedelta(minutes=5),
    )
    PostgresOfferCycleRepository(session).acquire_preparing(
        cycle,
        now=NOW,
        lease_expires_at=NOW + timedelta(minutes=5),
        claim_token="claim-token",
    )
    delivery_repo = PostgresWeeklyDigestDeliveryRepository(session)
    delivery = delivery_repo.reserve(
        identity.business_id, identity.owner_user_id, NOW.date(), NOW, 10
    )
    assert delivery is not None
    return (
        identity,
        recommendation,
        revision,
        cycle,
        delivery,
        delivery_repo,
        PostgresWeeklyDigestContentRepository(session),
    )


def _content(
    identity,
    recommendation,
    revision,
    cycle,
    delivery,
    version,
    at,
    *,
    member=None,
):
    return WeeklyDigestContent(
        uuid4(),
        delivery.id,
        identity.business_id,
        identity.owner_user_id,
        version,
        at,
        at,
        "person@example.test",
        f"Digest {version}",
        f"Immutable body {version}",
        f"<content-{delivery.id}-{version}@example.test>",
        (
            member
            or WeeklyDigestMember(
                identity.company_id,
                recommendation.id,
                revision.id,
                cycle.id,
                1,
            ),
        ),
    )


def test_content_repository_reads_exact_versions_and_members_under_business_scope(
    weekly_digest_content_database_url,
):
    with psycopg.connect(weekly_digest_content_database_url) as connection:
        (
            identity,
            recommendation,
            revision,
            cycle,
            delivery,
            delivery_repo,
            content_repo,
        ) = _setup(connection)
        first = _content(identity, recommendation, revision, cycle, delivery, 1, NOW)
        assert content_repo.append(first) == first
        assert (
            content_repo.get_by_id(identity.business_id, delivery.id, first.id) == first
        )
        assert content_repo.get_version(identity.business_id, delivery.id, 1) == first
        assert content_repo.get_current(identity.business_id, delivery.id) is None
        assert content_repo.list_versions(identity.business_id, delivery.id) == (first,)
        delivery = delivery_repo.select_content(
            identity.business_id, delivery.id, delivery.version, first.id, NOW
        )
        assert content_repo.get_current(identity.business_id, delivery.id) == first

        replacement = _content(
            identity,
            recommendation,
            revision,
            cycle,
            delivery,
            2,
            NOW + timedelta(minutes=1),
        )
        content_repo.append(replacement)
        delivery_repo.select_content(
            identity.business_id,
            delivery.id,
            delivery.version,
            replacement.id,
            replacement.created_at,
        )
        assert (
            content_repo.get_by_id(identity.business_id, delivery.id, first.id) == first
        )
        assert (
            content_repo.get_current(identity.business_id, delivery.id) == replacement
        )
        assert content_repo.list_versions(identity.business_id, delivery.id) == (
            first,
            replacement,
        )
        assert connection.execute(
            "SELECT subscription_updated_at,recipient,subject,body,message_id "
            "FROM operational.weekly_digest_contents WHERE id=%s",
            (first.id,),
        ).fetchone() == (
            first.subscription_updated_at,
            first.recipient,
            first.subject,
            first.body,
            first.message_id,
        )
        assert connection.execute(
            "SELECT company_id,recommendation_id,assessment_revision_id,offer_cycle_id,position "
            "FROM operational.weekly_digest_members WHERE content_id=%s",
            (first.id,),
        ).fetchall() == [
            (
                identity.company_id,
                recommendation.id,
                revision.id,
                cycle.id,
                1,
            )
        ]

        foreign_business = seed_prospecting_owner_company(connection).business_id
        assert content_repo.get_by_id(foreign_business, delivery.id, first.id) is None


def test_content_append_rejects_foreign_member_without_partial_content_write(
    weekly_digest_content_database_url,
):
    with psycopg.connect(weekly_digest_content_database_url) as connection:
        (
            identity,
            recommendation,
            revision,
            cycle,
            delivery,
            _delivery_repo,
            content_repo,
        ) = _setup(connection)
        foreign_identity, foreign_recommendation, foreign_revision = (
            seed_owned_recommendation_revision(
                connection, seed_prospecting_owner_company(connection)
            )
        )
        foreign_cycle = OfferCycle(
            uuid4(),
            foreign_identity.business_id,
            foreign_identity.company_id,
            foreign_recommendation.id,
            foreign_revision.id,
            f"foreign-cycle-{uuid4()}",
            "d" * 64,
            OfferCycleStatus("preparing"),
            NOW,
            NOW,
            "foreign-token",
            NOW + timedelta(minutes=5),
        )
        PostgresOfferCycleRepository(
            PsycopgDatabaseSession(connection)
        ).acquire_preparing(
            foreign_cycle,
            now=NOW,
            lease_expires_at=NOW + timedelta(minutes=5),
            claim_token="foreign-token",
        )
        invalid = _content(
            identity,
            recommendation,
            revision,
            cycle,
            delivery,
            1,
            NOW,
            member=WeeklyDigestMember(
                foreign_identity.company_id,
                foreign_recommendation.id,
                foreign_revision.id,
                foreign_cycle.id,
                1,
            ),
        )
        with pytest.raises(ConflictError), connection.transaction():
            content_repo.append(invalid)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_contents WHERE id=%s",
                (invalid.id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            content_repo.get_by_id(identity.business_id, delivery.id, invalid.id)
            is None
        )


def test_persisted_content_and_members_reject_mutation_and_deletion(
    weekly_digest_content_database_url,
):
    with psycopg.connect(weekly_digest_content_database_url) as connection:
        identity, recommendation, revision, cycle, delivery, _, content_repo = _setup(
            connection
        )
        content = _content(identity, recommendation, revision, cycle, delivery, 1, NOW)
        content_repo.append(content)
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.weekly_digest_contents SET body='rewritten' WHERE id=%s",
                (content.id,),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM operational.weekly_digest_members WHERE content_id=%s",
                (content.id,),
            )
        assert (
            content_repo.get_by_id(identity.business_id, delivery.id, content.id)
            == content
        )
