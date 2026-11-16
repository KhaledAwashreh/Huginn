from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from huginn.management.persistence.repositories.prospect import (
    PostgresProspectRepository,
)
from huginn.management.persistence.repositories.prospect_activity import (
    PostgresProspectActivityRepository,
)
from huginn.management.persistence.repositories.prospect_origin import (
    PostgresProspectOriginRepository,
)
from huginn.management.persistence.repositories.recommendation import (
    PostgresRecommendationRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_assessment_revision,
    valid_prospect,
    valid_prospect_activity,
    valid_prospect_origin,
    valid_recommendation,
)


def test_exact_origin_and_activity_request_idempotency(management_database_url):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendations = PostgresRecommendationRepository(session)
        revisions = PostgresAssessmentRevisionRepository(session)
        prospects = PostgresProspectRepository(session)
        origins = PostgresProspectOriginRepository(session)
        activities = PostgresProspectActivityRepository(session)
        recommendation = recommendations.create_open(valid_recommendation(identity))
        revision = valid_assessment_revision(identity, recommendation)
        revisions.append(revision)
        prospect = prospects.create(valid_prospect(identity))
        origin = valid_prospect_origin(identity, recommendation, revision, prospect)

        first = origins.append_if_absent(origin)
        assert first.created is True
        second = origins.append_if_absent(replace(origin, id=uuid4()))
        assert second.created is False
        assert second.origin == origin
        assert origins.list_owned(identity.business_id, prospect.id) == (origin,)
        other_identity = seed_prospecting_owner_company(connection)
        assert origins.list_owned(other_identity.business_id, prospect.id) == ()
        with pytest.raises(NotFoundError):
            origins.append_if_absent(
                replace(origin, business_id=other_identity.business_id)
            )

        activity = valid_prospect_activity(identity, prospect, origin_id=origin.id)
        command = CommandIdentity("save-request-a", "a" * 64)
        inserted = activities.append_once(
            identity.business_id, prospect.id, command, activity
        )
        assert inserted == activity
        replay = activities.append_once(
            identity.business_id,
            prospect.id,
            CommandIdentity("save-request-b", "b" * 64),
            replace(activity, id=uuid4()),
        )
        assert replay == activity
        assert activities.list_owned(identity.business_id, prospect.id) == (activity,)
        assert (
            activities.get_owned(identity.business_id, prospect.id, activity.id)
            == activity
        )
        assert (
            activities.get_owned(other_identity.business_id, prospect.id, activity.id)
            is None
        )
        assert activities.get_owned(identity.business_id, uuid4(), activity.id) is None
        assert activities.get_owned(identity.business_id, prospect.id, uuid4()) is None

        with pytest.raises(ConflictError):
            # Reused request identity is checked before exact-origin de-duplication.
            activities.append_once(
                identity.business_id,
                prospect.id,
                CommandIdentity("save-request-a", "c" * 64),
                replace(activity, id=uuid4()),
            )


def test_saved_activity_cannot_replay_an_origin_from_another_business(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        owner_a = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendations = PostgresRecommendationRepository(session)
        revisions = PostgresAssessmentRevisionRepository(session)
        prospects = PostgresProspectRepository(session)
        origins = PostgresProspectOriginRepository(session)
        activities = PostgresProspectActivityRepository(session)

        recommendation_a = recommendations.create_open(valid_recommendation(owner_a))
        revision_a = valid_assessment_revision(owner_a, recommendation_a)
        revisions.append(revision_a)
        prospect_a = prospects.create(valid_prospect(owner_a))
        origin_a = valid_prospect_origin(
            owner_a, recommendation_a, revision_a, prospect_a
        )
        origins.append_if_absent(origin_a)
        activity_a = valid_prospect_activity(owner_a, prospect_a, origin_id=origin_a.id)
        activities.append_once(
            owner_a.business_id,
            prospect_a.id,
            CommandIdentity("owner-a-save", "a" * 64),
            activity_a,
        )

        owner_b = seed_prospecting_owner_company(connection)
        prospect_b = prospects.create(valid_prospect(owner_b))
        forged_activity = valid_prospect_activity(
            owner_b, prospect_b, origin_id=origin_a.id
        )
        with pytest.raises(NotFoundError):
            activities.append_once(
                owner_b.business_id,
                prospect_b.id,
                CommandIdentity("owner-b-forged-origin", "b" * 64),
                forged_activity,
            )

        assert activities.list_owned(owner_b.business_id, prospect_b.id) == ()
        assert activities.list_owned(owner_a.business_id, prospect_a.id) == (
            activity_a,
        )


def test_reused_request_key_conflict_wins_over_origin_dedup_across_connections(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendation = PostgresRecommendationRepository(session).create_open(
            valid_recommendation(identity)
        )
        revision = valid_assessment_revision(identity, recommendation)
        PostgresAssessmentRevisionRepository(session).append(revision)
        prospect = PostgresProspectRepository(session).create(valid_prospect(identity))
        origin = valid_prospect_origin(identity, recommendation, revision, prospect)
        PostgresProspectOriginRepository(session).append_if_absent(origin)
        connection.commit()
    barrier = Barrier(2)

    def append_with_fingerprint(fingerprint):
        with psycopg.connect(management_database_url) as connection:
            activity = valid_prospect_activity(identity, prospect, origin_id=origin.id)
            barrier.wait()
            repository = PostgresProspectActivityRepository(
                PsycopgDatabaseSession(connection)
            )
            try:
                result = repository.append_once(
                    identity.business_id,
                    prospect.id,
                    CommandIdentity("same-command-key", fingerprint),
                    activity,
                )
            except ConflictError:
                return "conflict", None
            return "created", result

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(workers.map(append_with_fingerprint, ("c" * 64, "d" * 64)))
    created = [value for outcome, value in results if outcome == "created"]
    assert len(created) == 1
    assert [outcome for outcome, _ in results].count("conflict") == 1
    with psycopg.connect(management_database_url) as connection:
        persisted = PostgresProspectActivityRepository(
            PsycopgDatabaseSession(connection)
        ).list_owned(identity.business_id, prospect.id)
    assert persisted == (created[0],)


def test_activity_request_replay_rejects_changed_fingerprint(management_database_url):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        prospects = PostgresProspectRepository(session)
        activities = PostgresProspectActivityRepository(session)
        prospect = prospects.create(valid_prospect(identity))
        activity = valid_prospect_activity(
            identity, prospect, kind=ActivityKind("note_added")
        )
        activities.append_once(
            identity.business_id,
            prospect.id,
            CommandIdentity("note-request", "d" * 64),
            activity,
        )
        with pytest.raises(ConflictError):
            activities.append_once(
                identity.business_id,
                prospect.id,
                CommandIdentity("note-request", "e" * 64),
                replace(activity, id=uuid4()),
            )


def test_origin_append_deduplicates_exact_origin_across_connections(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendation = PostgresRecommendationRepository(session).create_open(
            valid_recommendation(identity)
        )
        revision = valid_assessment_revision(identity, recommendation)
        PostgresAssessmentRevisionRepository(session).append(revision)
        prospect = PostgresProspectRepository(session).create(valid_prospect(identity))
        origin = valid_prospect_origin(identity, recommendation, revision, prospect)
        connection.commit()
    barrier = Barrier(2)

    def append_origin():
        with psycopg.connect(management_database_url) as connection:
            barrier.wait()
            repository = PostgresProspectOriginRepository(
                PsycopgDatabaseSession(connection)
            )
            return repository.append_if_absent(replace(origin, id=uuid4()))

    with ThreadPoolExecutor(max_workers=2) as workers:
        first, second = workers.map(lambda _: append_origin(), range(2))
    assert {first.created, second.created} == {False, True}
    assert first.origin == second.origin
    with psycopg.connect(management_database_url) as connection:
        persisted = PostgresProspectOriginRepository(
            PsycopgDatabaseSession(connection)
        ).list_owned(identity.business_id, prospect.id)
    assert persisted == (first.origin,)
