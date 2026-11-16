from concurrent.futures import ThreadPoolExecutor
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
NOW = datetime(2050, 1, 3, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def weekly_digest_delivery_database_url():
    with provisioned_postgres("huginn_weekly_delivery_repository_test") as url:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(_LEGACY_RECOMMENDATIONS_SCHEMA.read_text())
            connection.execute(_WEEKLY_SCHEMA.read_text())
            connection.execute(_CONTENT_SCHEMA.read_text())
        yield url


def _setup(connection):
    identity, recommendation, revision = seed_owned_recommendation_revision(connection)
    session = PsycopgDatabaseSession(connection)
    offer_cycles = PostgresOfferCycleRepository(session)
    cycle_id = uuid4()
    cycle = OfferCycle(
        cycle_id,
        identity.business_id,
        identity.company_id,
        recommendation.id,
        revision.id,
        f"weekly-cycle-{uuid4()}",
        "b" * 64,
        OfferCycleStatus("preparing"),
        NOW,
        NOW,
        "claim-token",
        NOW + timedelta(minutes=5),
    )
    offer_cycles.acquire_preparing(
        cycle,
        now=NOW,
        lease_expires_at=NOW + timedelta(minutes=5),
        claim_token="claim-token",
    )
    return (
        identity,
        recommendation,
        revision,
        cycle,
        PostgresWeeklyDigestDeliveryRepository(session),
        PostgresWeeklyDigestContentRepository(session),
    )


def _content(identity, recommendation, revision, cycle, delivery, version, at):
    member = WeeklyDigestMember(
        identity.company_id,
        recommendation.id,
        revision.id,
        cycle.id,
        1,
    )
    return WeeklyDigestContent(
        uuid4(),
        delivery.id,
        identity.business_id,
        identity.owner_user_id,
        version,
        at,
        at,
        "digest@example.test",
        f"Weekly digest {version}",
        f"Frozen content version {version}",
        f"<weekly-{delivery.id}-{version}@example.test>",
        (member,),
    )


def test_delivery_repository_reserves_by_business_week_and_records_events(
    weekly_digest_delivery_database_url,
):
    with psycopg.connect(weekly_digest_delivery_database_url) as connection:
        identity, _, _, _, delivery_repo, _ = _setup(connection)
        week_start = NOW.date()
        delivery = delivery_repo.reserve(
            identity.business_id, identity.owner_user_id, week_start, NOW, 10
        )
        assert delivery is not None
        assert delivery.state == "preparing"
        assert delivery.version == 1
        assert delivery.current_content_id is None
        assert (
            delivery_repo.reserve(
                identity.business_id, identity.owner_user_id, week_start, NOW, 10
            )
            is None
        )

        other_identity = seed_prospecting_owner_company(connection)
        assert (
            delivery_repo.reserve(
                identity.business_id, other_identity.owner_user_id, week_start, NOW, 10
            )
            is None
        )
        assert (
            delivery_repo.get_for_business(other_identity.business_id, delivery.id)
            is None
        )
        assert (
            delivery_repo.get_for_business(identity.business_id, delivery.id)
            == delivery
        )
        assert (
            delivery_repo.get_for_update(identity.business_id, delivery.id) == delivery
        )
        assert (
            delivery_repo.list_events(identity.business_id, delivery.id)[0].event_kind
            == "reserved"
        )

        assert connection.execute(
            "SELECT business_id,recipient_user_id,week_start,state,version "
            "FROM operational.weekly_digest_deliveries WHERE id=%s",
            (delivery.id,),
        ).fetchone() == (
            identity.business_id,
            identity.owner_user_id,
            week_start,
            "preparing",
            1,
        )
        assert connection.execute(
            "SELECT delivery_version,event_kind,actor_user_id "
            "FROM operational.weekly_digest_delivery_events WHERE delivery_id=%s",
            (delivery.id,),
        ).fetchall() == [(1, "reserved", None)]


def test_delivery_lifecycle_cas_and_unknown_recovery_preserve_actual_acceptance(
    weekly_digest_delivery_database_url,
):
    with psycopg.connect(weekly_digest_delivery_database_url) as connection:
        identity, recommendation, revision, cycle, delivery_repo, content_repo = _setup(
            connection
        )
        delivery = delivery_repo.reserve(
            identity.business_id, identity.owner_user_id, NOW.date(), NOW, 10
        )
        assert delivery is not None
        first = _content(identity, recommendation, revision, cycle, delivery, 1, NOW)
        content_repo.append(first)
        delivery = delivery_repo.select_content(
            identity.business_id, delivery.id, 1, first.id, NOW
        )
        assert delivery.version == 2
        assert delivery.current_content_id == first.id
        assert (
            delivery_repo.list_events(identity.business_id, delivery.id)[-1].event_kind
            == "content_prepared"
        )

        replacement = _content(
            identity,
            recommendation,
            revision,
            cycle,
            delivery,
            2,
            NOW + timedelta(seconds=1),
        )
        content_repo.append(replacement)
        with pytest.raises(ConflictError):
            delivery_repo.select_content(
                identity.business_id, delivery.id, 1, replacement.id, NOW
            )
        delivery = delivery_repo.select_content(
            identity.business_id,
            delivery.id,
            delivery.version,
            replacement.id,
            NOW + timedelta(seconds=1),
        )
        assert delivery.version == 3
        assert delivery.current_content_id == replacement.id

        started_at = NOW + timedelta(seconds=2)
        delivery = delivery_repo.authorize_sending(
            identity.business_id,
            delivery.id,
            delivery.version,
            replacement.id,
            started_at,
        )
        assert delivery.state == "sending"
        assert delivery.version == 4
        with pytest.raises(ConflictError):
            delivery_repo.authorize_sending(
                identity.business_id,
                delivery.id,
                delivery.version,
                replacement.id,
                started_at + timedelta(seconds=1),
            )

        unknown_at = started_at + timedelta(seconds=4)
        delivery = delivery_repo.settle(
            identity.business_id,
            delivery.id,
            delivery.version,
            "unknown",
            unknown_at,
        )
        accepted_at = started_at + timedelta(seconds=3)
        recovered_at = NOW + timedelta(hours=1)
        foreign_identity = seed_prospecting_owner_company(connection)
        with pytest.raises(ConflictError):
            delivery_repo.resolve_unknown(
                identity.business_id,
                delivery.id,
                delivery.version,
                foreign_identity.owner_user_id,
                "Not an owner",
                "sent",
                recovered_at,
                accepted_at,
            )
        assert (
            delivery_repo.get_for_business(identity.business_id, delivery.id)
            == delivery
        )
        delivery = delivery_repo.resolve_unknown(
            identity.business_id,
            delivery.id,
            delivery.version,
            identity.owner_user_id,
            "Provider confirmed prior acceptance",
            "sent",
            recovered_at,
            accepted_at,
        )
        assert (delivery.state, delivery.settled_at, delivery.accepted_at) == (
            "sent",
            recovered_at,
            accepted_at,
        )
        events = delivery_repo.list_events(identity.business_id, delivery.id)
        resolution = events[-1]
        assert (
            resolution.event_kind,
            resolution.actor_user_id,
            resolution.outcome,
        ) == (
            "unknown_resolved",
            identity.owner_user_id,
            "sent",
        )
        assert resolution.recorded_at == recovered_at
        assert resolution.accepted_at == accepted_at
        with pytest.raises(ConflictError):
            delivery_repo.settle(
                identity.business_id,
                delivery.id,
                delivery.version,
                "unknown",
                recovered_at + timedelta(seconds=1),
            )

        assert connection.execute(
            "SELECT state,version,sending_started_at,settled_at,accepted_at "
            "FROM operational.weekly_digest_deliveries WHERE id=%s",
            (delivery.id,),
        ).fetchone() == (
            "sent",
            delivery.version,
            started_at,
            recovered_at,
            accepted_at,
        )
        assert connection.execute(
            "SELECT event_kind,recorded_at,accepted_at,actor_user_id,reason "
            "FROM operational.weekly_digest_delivery_events "
            "WHERE delivery_id=%s ORDER BY delivery_version",
            (delivery.id,),
        ).fetchall() == [
            ("reserved", NOW, None, None, None),
            ("content_prepared", NOW, None, None, None),
            ("content_replaced", NOW + timedelta(seconds=1), None, None, None),
            ("sending_authorized", started_at, None, None, None),
            ("unknown", unknown_at, None, None, None),
            (
                "unknown_resolved",
                recovered_at,
                accepted_at,
                identity.owner_user_id,
                "Provider confirmed prior acceptance",
            ),
        ]


def test_global_daily_budget_is_serialized_across_businesses_and_connections(
    weekly_digest_delivery_database_url,
):
    now = datetime.now(UTC) + timedelta(days=400)
    now += timedelta(days=(-now.weekday()) % 7)
    now = now.replace(hour=12, minute=0, second=0, microsecond=0)
    with psycopg.connect(weekly_digest_delivery_database_url) as connection:
        first = seed_prospecting_owner_company(connection)
        second = seed_prospecting_owner_company(connection)

    def reserve(identity):
        with psycopg.connect(weekly_digest_delivery_database_url) as connection:
            repository = PostgresWeeklyDigestDeliveryRepository(
                PsycopgDatabaseSession(connection)
            )
            return repository.reserve(
                identity.business_id,
                identity.owner_user_id,
                now.date(),
                now,
                1,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, (first, second)))
    assert sum(value is not None for value in outcomes) == 1
    with psycopg.connect(weekly_digest_delivery_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_deliveries "
                "WHERE created_at=%s",
                (now,),
            ).fetchone()[0]
            == 1
        )
