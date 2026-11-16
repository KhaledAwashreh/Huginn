from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from huginn.management.persistence.repositories.recommendation import (
    PostgresRecommendationRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_assessment_revision,
    valid_recommendation,
)


def test_recommendation_crud_is_business_scoped_and_version_checked(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        repository = PostgresRecommendationRepository(
            PsycopgDatabaseSession(connection)
        )
        recommendation = valid_recommendation(identity)

        created = repository.create_open(recommendation)
        assert created == recommendation
        assert repository.get_owned(identity.business_id, created.id) == created
        assert repository.get_open(identity.business_id, identity.company_id) == created
        assert repository.get_owned(identity.business_id, uuid4()) is None

        with pytest.raises(NotFoundError):
            repository.select_current_revision(
                identity.business_id, created.id, uuid4(), 1
            )

        resolved_at = datetime.now(UTC) + timedelta(seconds=1)
        resolved = repository.resolve_owned(
            identity.business_id,
            created.id,
            created.version,
            RecommendationStatus("rejected"),
            identity.owner_user_id,
            resolved_at,
            "Not relevant",
        )
        assert resolved.status.value == "rejected"
        assert resolved.version == created.version + 1
        assert repository.get_open(identity.business_id, identity.company_id) is None
        with pytest.raises(ConflictError):
            repository.resolve_owned(
                identity.business_id,
                created.id,
                created.version,
                RecommendationStatus("converted"),
                identity.owner_user_id,
                resolved_at + timedelta(seconds=1),
                None,
            )
        assert repository.get_owned(uuid4(), created.id) is None


def test_create_open_reuses_the_business_company_occurrence(management_database_url):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        repository = PostgresRecommendationRepository(
            PsycopgDatabaseSession(connection)
        )
        first = repository.create_open(valid_recommendation(identity))
        second = repository.create_open(valid_recommendation(identity))
        assert second == first


def test_create_open_serializes_same_business_company_on_separate_connections(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        connection.commit()
    barrier = Barrier(2)

    def create_occurrence():
        with psycopg.connect(management_database_url) as connection:
            barrier.wait()
            repository = PostgresRecommendationRepository(
                PsycopgDatabaseSession(connection)
            )
            return repository.create_open(valid_recommendation(identity))

    with ThreadPoolExecutor(max_workers=2) as workers:
        first, second = workers.map(lambda _: create_occurrence(), range(2))
    assert first == second
    with psycopg.connect(management_database_url) as connection:
        persisted = PostgresRecommendationRepository(
            PsycopgDatabaseSession(connection)
        ).get_open(identity.business_id, identity.company_id)
    assert persisted == first


def test_late_confirmed_handoff_records_first_exposure_without_reopening(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendations = PostgresRecommendationRepository(session)
        revisions = PostgresAssessmentRevisionRepository(session)
        recommendation = recommendations.create_open(valid_recommendation(identity))
        revision = valid_assessment_revision(identity, recommendation)
        revisions.append(revision)
        recommendation = recommendations.select_current_revision(
            identity.business_id, recommendation.id, revision.id, recommendation.version
        )

        authorized_at = datetime.now(UTC)
        rejection_at = authorized_at + timedelta(seconds=2)
        presented_at = authorized_at + timedelta(seconds=3)
        settled_at = authorized_at + timedelta(seconds=4)
        cycle_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycles "
            "(id,business_id,company_id,recommendation_id,selected_revision_id,"
            "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
            "claim_token,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,%s,'repo-late-handoff',%s,'preparing',%s,%s,'token',%s)",
            (
                cycle_id,
                identity.business_id,
                identity.company_id,
                recommendation.id,
                revision.id,
                "1" * 64,
                authorized_at,
                authorized_at,
                authorized_at + timedelta(minutes=5),
            ),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='sending',updated_at=%s,"
            "lease_expires_at=NULL,sending_started_at=%s WHERE id=%s",
            (
                authorized_at + timedelta(seconds=1),
                authorized_at + timedelta(seconds=1),
                cycle_id,
            ),
        )
        rejected = recommendations.resolve_owned(
            identity.business_id,
            recommendation.id,
            recommendation.version,
            RecommendationStatus("rejected"),
            identity.owner_user_id,
            rejection_at,
            "Not relevant",
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='confirmed',updated_at=%s,"
            "settled_at=%s,presented_at=%s WHERE id=%s",
            (settled_at, settled_at, presented_at, cycle_id),
        )

        persisted = recommendations.record_confirmed_presentation(
            identity.business_id,
            identity.company_id,
            recommendation.id,
            cycle_id,
            revision.id,
            presented_at,
        )
        assert persisted.status.value == "rejected"
        assert persisted.first_presented_at == presented_at
        assert persisted.resolved_at == rejected.resolved_at == rejection_at
        assert persisted.resolved_by_user_id == identity.owner_user_id
        assert persisted.resolution_reason == "Not relevant"
        assert persisted.current_revision_id == revision.id
