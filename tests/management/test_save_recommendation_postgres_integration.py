from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
    PsycopgDatabaseSession,
)
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from huginn.management.persistence.repositories.recommendation import (
    PostgresRecommendationRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
    valid_assessment_revision,
)

TABLES = ("prospects", "prospect_origins", "prospect_activities", "command_receipts")


def _setup(database_url, *, identity=None):
    with psycopg.connect(database_url) as connection:
        return seed_owned_recommendation_revision(connection, identity)


def _factory(database_url):
    return ManagementConnectionFactory(database_url, statement_timeout_ms=5000)


def _service(database_url, work_type=PostgresProspectingUnitOfWork):
    return SaveRecommendationService(lambda: work_type(_factory(database_url)))


def _principal(identity):
    return Principal(identity.account_id, identity.owner_user_id)


def _counts(connection, business_id):
    return tuple(
        connection.execute(
            f"SELECT count(*) FROM operational.{table} WHERE business_id=%s",
            (business_id,),
        ).fetchone()[0]
        for table in TABLES
    )


def test_save_shown_historical_revision_and_second_origin_keep_one_relationship(
    management_database_url,
):
    identity, recommendation, shown_revision = _setup(management_database_url)
    with PostgresProspectingUnitOfWork(_factory(management_database_url)) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        newest = work.assessment_revisions.append(
            valid_assessment_revision(identity, recommendation, revision_number=2)
        )
        work.recommendations.select_current_revision(
            identity.business_id, recommendation.id, newest.id, recommendation.version
        )
        work.commit()
    first = _service(management_database_url).execute(
        _principal(identity),
        SaveRecommendationRequest(
            recommendation.id, shown_revision.id, "save-original"
        ),
    )
    with PostgresProspectingUnitOfWork(_factory(management_database_url)) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        prospect = work.prospects.get_owned(identity.business_id, first.prospect_id)
        changed = replace(
            prospect,
            stage=ProspectStage("contacted"),
            version=prospect.version + 1,
            updated_at=datetime.now(UTC),
            notes="Keep these notes",
            follow_up_at=datetime.now(UTC) + timedelta(days=3),
        )
        work.prospects.update_owned(
            identity.business_id, prospect.id, prospect.version, changed
        )
        work.commit()
    second = _service(management_database_url).execute(
        _principal(identity),
        SaveRecommendationRequest(recommendation.id, newest.id, "save-new-origin"),
    )
    assert second.prospect_id == first.prospect_id
    assert second.prospect_stage == "contacted"
    assert second.prospect_version == 2
    with psycopg.connect(management_database_url) as connection:
        assert _counts(connection, identity.business_id) == (1, 2, 2, 2)
        assert set(
            connection.execute(
                "SELECT assessment_revision_id FROM operational.prospect_origins WHERE business_id=%s",
                (identity.business_id,),
            ).fetchall()
        ) == {(shown_revision.id,), (newest.id,)}
        assert connection.execute(
            "SELECT status,current_revision_id FROM operational.recommendations WHERE id=%s",
            (recommendation.id,),
        ).fetchone() == ("converted", newest.id)
        assert connection.execute(
            "SELECT actor_user_id,payload->>'assessment_revision_id' FROM operational.prospect_activities WHERE business_id=%s ORDER BY recorded_at,id",
            (identity.business_id,),
        ).fetchall() == [
            (identity.owner_user_id, str(shown_revision.id)),
            (identity.owner_user_id, str(newest.id)),
        ]
        assert connection.execute(
            "SELECT notes,follow_up_at FROM operational.prospects WHERE id=%s",
            (first.prospect_id,),
        ).fetchone() == (changed.notes, changed.follow_up_at)
        revisions = PostgresAssessmentRevisionRepository(
            PsycopgDatabaseSession(connection)
        ).list_history(identity.business_id, recommendation.id)
        assert revisions == (shown_revision, newest)


def test_committed_retry_returns_its_original_result_after_current_stage_changes(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    request = SaveRecommendationRequest(recommendation.id, revision.id, "lost-response")
    first = _service(management_database_url).execute(_principal(identity), request)
    with PostgresProspectingUnitOfWork(_factory(management_database_url)) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        prospect = work.prospects.get_owned(identity.business_id, first.prospect_id)
        work.prospects.update_owned(
            identity.business_id,
            prospect.id,
            prospect.version,
            replace(
                prospect,
                stage=ProspectStage("contacted"),
                version=2,
                updated_at=datetime.now(UTC),
            ),
        )
        work.commit()
    replay = _service(management_database_url).execute(_principal(identity), request)
    assert replay == first
    assert replay.prospect_stage == "saved"
    with psycopg.connect(management_database_url) as connection:
        assert _counts(connection, identity.business_id) == (1, 1, 1, 1)
        assert connection.execute(
            "SELECT stage,version FROM operational.prospects WHERE id=%s",
            (first.prospect_id,),
        ).fetchone() == ("contacted", 2)


def test_concurrent_distinct_keys_for_same_revision_commit_one_origin_and_action(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    barrier = Barrier(2, timeout=5)

    def save(index):
        barrier.wait()
        return _service(management_database_url).execute(
            _principal(identity),
            SaveRecommendationRequest(
                recommendation.id, revision.id, f"concurrent-{index}"
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(save, range(2)))
    assert results[0].prospect_id == results[1].prospect_id
    assert results[0].origin_id == results[1].origin_id
    with psycopg.connect(management_database_url) as connection:
        assert _counts(connection, identity.business_id) == (1, 1, 1, 2)


def test_cross_company_same_key_conflict_rolls_back_losing_partial_save(
    management_database_url,
):
    identity, first_rec, first_rev = _setup(management_database_url)
    with psycopg.connect(management_database_url) as connection:
        company_id = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Other save') RETURNING id",
            (f"{uuid4()}.example.test",),
        ).fetchone()[0]
    second_identity = replace(identity, company_id=company_id)
    _, second_rec, second_rev = _setup(
        management_database_url, identity=second_identity
    )
    barrier = Barrier(2, timeout=5)

    class FencedWork(PostgresProspectingUnitOfWork):
        def __enter__(self):
            super().__enter__()
            activities = self.activities

            def append(*args):
                barrier.wait()
                return activities.append_once(*args)

            self.activities = SimpleNamespace(append_once=append)
            return self

    def save(pair):
        rec, rev = pair
        try:
            return _service(management_database_url, FencedWork).execute(
                _principal(identity),
                SaveRecommendationRequest(rec.id, rev.id, "same-business-key"),
            )
        except ConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(save, ((first_rec, first_rev), (second_rec, second_rev)))
        )
    assert sum(result is not None for result in results) == 1
    winner = next(result for result in results if result is not None)
    with psycopg.connect(management_database_url) as connection:
        assert _counts(connection, identity.business_id) == (1, 1, 1, 1)
        assert set(
            connection.execute(
                "SELECT id,status FROM operational.recommendations WHERE business_id=%s",
                (identity.business_id,),
            ).fetchall()
        ) == {
            (
                first_rec.id,
                "converted" if winner.recommendation_id == first_rec.id else "open",
            ),
            (
                second_rec.id,
                "converted" if winner.recommendation_id == second_rec.id else "open",
            ),
        }
        assert connection.execute(
            "SELECT company_id FROM operational.prospects WHERE business_id=%s",
            (identity.business_id,),
        ).fetchone() == (winner.company_id,)


def test_historical_rejection_and_independent_blocks_survive_explicit_save(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    with PostgresProspectingUnitOfWork(_factory(management_database_url)) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        rejected = work.recommendations.resolve_owned(
            identity.business_id,
            recommendation.id,
            recommendation.version,
            RecommendationStatus("rejected"),
            identity.owner_user_id,
            datetime.now(UTC),
            "Original rejection",
        )
        now = datetime.now(UTC)
        blocks = tuple(
            work.suppression_blocks.append(
                SuppressionBlock(
                    uuid4(),
                    identity.business_id,
                    identity.company_id,
                    SuppressionKind(kind),
                    now,
                    created_by_user_id=identity.owner_user_id,
                    expires_at=expiry,
                )
            )
            for kind, expiry in (
                ("rejection", None),
                ("pause", now + timedelta(days=10)),
                ("cooldown", now + timedelta(days=30)),
            )
        )
        work.commit()
    result = _service(management_database_url).execute(
        _principal(identity),
        SaveRecommendationRequest(recommendation.id, revision.id, "historical-save"),
    )
    assert result.recommendation_status == "rejected"
    with PostgresProspectingUnitOfWork(_factory(management_database_url)) as work:
        assert (
            work.recommendations.get_owned(identity.business_id, recommendation.id)
            == rejected
        )
        assert set(
            work.suppression_blocks.list_history(
                identity.business_id, identity.company_id
            )
        ) == set(blocks)
        assert (
            work.prospects.get_owned(
                identity.business_id, result.prospect_id
            ).stage.value
            == "saved"
        )


def test_failure_after_receipt_insert_rolls_back_every_save_record(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)

    class InjectedFailure(Exception):
        pass

    class FailingWork(PostgresProspectingUnitOfWork):
        def __enter__(self):
            super().__enter__()
            commands = self.commands

            def record(receipt):
                commands.record(receipt)
                raise InjectedFailure

            self.commands = SimpleNamespace(
                get_by_key=commands.get_by_key, record=record
            )
            return self

    with pytest.raises(InjectedFailure):
        _service(management_database_url, FailingWork).execute(
            _principal(identity),
            SaveRecommendationRequest(recommendation.id, revision.id, "rollback-all"),
        )
    with psycopg.connect(management_database_url) as connection:
        assert _counts(connection, identity.business_id) == (0, 0, 0, 0)
        assert (
            PostgresRecommendationRepository(
                PsycopgDatabaseSession(connection)
            ).get_owned(identity.business_id, recommendation.id)
            == recommendation
        )


def test_foreign_owned_recommendation_is_not_found_without_any_command_writes(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    other_identity, _, _ = _setup(management_database_url)
    with pytest.raises(NotFoundError):
        _service(management_database_url).execute(
            _principal(other_identity),
            SaveRecommendationRequest(recommendation.id, revision.id, "foreign-save"),
        )
    with psycopg.connect(management_database_url) as connection:
        assert _counts(connection, identity.business_id) == (0, 0, 0, 0)
        assert _counts(connection, other_identity.business_id) == (0, 0, 0, 0)
