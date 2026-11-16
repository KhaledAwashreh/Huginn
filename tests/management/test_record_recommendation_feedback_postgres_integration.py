from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.requests.record_recommendation_feedback_request import (
    RecordRecommendationFeedbackRequest,
)
from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.record_recommendation_feedback_service import (
    RecordRecommendationFeedbackService,
)
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
    valid_assessment_revision,
)


def _setup(database_url):
    with psycopg.connect(database_url) as connection:
        identity, recommendation, revision = seed_owned_recommendation_revision(
            connection
        )
        association = revision.strategy_assessments[0]
        connection.execute(
            "INSERT INTO operational.service_offerings(id,business_id,name,description) VALUES (%s,%s,'Research','Research services')",
            (association.offering_id, identity.business_id),
        )
        connection.execute(
            "INSERT INTO operational.ideal_client_profiles(id,business_id,name) VALUES (%s,%s,'Configured ICP')",
            (association.ideal_client_profile_id, identity.business_id),
        )
        connection.execute(
            "INSERT INTO operational.client_discovery_strategies(id,business_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,%s,'Keep inactive',%s,%s,false)",
            (
                association.strategy_id,
                identity.business_id,
                association.offering_id,
                association.ideal_client_profile_id,
            ),
        )
        return identity, recommendation, revision


def _work(database_url, work_type=PostgresProspectingUnitOfWork):
    return lambda: work_type(
        ManagementConnectionFactory(database_url, statement_timeout_ms=5000)
    )


def _principal(identity):
    return Principal(identity.account_id, identity.owner_user_id)


def _snapshot(connection, identity):
    return {
        table: connection.execute(
            f"SELECT to_jsonb(t) FROM operational.{table} t WHERE {key}=%s ORDER BY to_jsonb(t)::text",
            (value,),
        ).fetchall()
        for table, key, value in (
            ("users", "id", identity.owner_user_id),
            ("businesses", "id", identity.business_id),
            (
                "business_recommendation_preferences",
                "business_id",
                identity.business_id,
            ),
            ("service_offerings", "business_id", identity.business_id),
            ("ideal_client_profiles", "business_id", identity.business_id),
            ("client_discovery_strategies", "business_id", identity.business_id),
            ("recommendations", "business_id", identity.business_id),
            ("assessment_revisions", "business_id", identity.business_id),
            ("prospects", "business_id", identity.business_id),
            ("prospect_origins", "business_id", identity.business_id),
            ("prospect_activities", "business_id", identity.business_id),
            ("suppression_blocks", "business_id", identity.business_id),
        )
    }


@pytest.mark.parametrize(
    "feedback",
    [
        RecommendationFeedback("useful"),
        RecommendationFeedback("useful", next_step="save", outcome="not_relevant"),
        RecommendationFeedback("not_useful", next_step="contact", outcome="won"),
        RecommendationFeedback("unsure", next_step="skip", outcome="won"),
    ],
)
def test_feedback_persists_on_shown_historical_revision_without_canonical_side_effects(
    management_database_url, feedback
):
    identity, recommendation, shown_revision = _setup(management_database_url)
    with _work(management_database_url)() as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        newest = work.assessment_revisions.append(
            valid_assessment_revision(identity, recommendation, revision_number=2)
        )
        work.recommendations.select_current_revision(
            identity.business_id, recommendation.id, newest.id, recommendation.version
        )
        work.commit()
    with psycopg.connect(management_database_url) as connection:
        before = _snapshot(connection, identity)
    request = RecordRecommendationFeedbackRequest(
        recommendation.id, shown_revision.id, "feedback-original", feedback
    )
    response = RecordRecommendationFeedbackService(
        _work(management_database_url)
    ).execute(_principal(identity), request)
    assert response.feedback.assessment_revision_id == shown_revision.id
    assert response.feedback.actor_user_id == identity.owner_user_id
    assert response.feedback.feedback == feedback
    with psycopg.connect(management_database_url) as connection:
        assert _snapshot(connection, identity) == before
        assert connection.execute(
            "SELECT recommendation_id,assessment_revision_id,actor_user_id,payload FROM operational.recommendation_assessment_feedback WHERE id=%s",
            (response.feedback.id,),
        ).fetchone() == (
            recommendation.id,
            shown_revision.id,
            identity.owner_user_id,
            {
                "usefulness": feedback.usefulness,
                "reasons": list(feedback.reasons),
                "correction": feedback.correction,
                "next_step": feedback.next_step,
                "outcome": feedback.outcome,
                "notes": feedback.notes,
            },
        )
        assert connection.execute(
            "SELECT resource_id,resource_version,result_snapshot FROM operational.command_receipts WHERE business_id=%s AND idempotency_key=%s",
            (identity.business_id, request.request_key),
        ).fetchone() == (response.feedback.id, 1, response.snapshot().to_json_object())


def test_feedback_retry_is_immutable_and_shared_key_conflicts_with_save(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    service = RecordRecommendationFeedbackService(_work(management_database_url))
    request = RecordRecommendationFeedbackRequest(
        recommendation.id,
        revision.id,
        "shared-key",
        RecommendationFeedback("useful", notes="Retain original note"),
    )
    first = service.execute(_principal(identity), request)
    with _work(management_database_url)() as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        newest = work.assessment_revisions.append(
            valid_assessment_revision(identity, recommendation, revision_number=2)
        )
        work.recommendations.select_current_revision(
            identity.business_id, recommendation.id, newest.id, recommendation.version
        )
        work.commit()
    assert service.execute(_principal(identity), request) == first
    with pytest.raises(ConflictError):
        service.execute(
            _principal(identity),
            replace(request, feedback=RecommendationFeedback("not_useful")),
        )
    with pytest.raises(ConflictError):
        SaveRecommendationService(_work(management_database_url)).execute(
            _principal(identity),
            SaveRecommendationRequest(recommendation.id, revision.id, "shared-key"),
        )
    with psycopg.connect(management_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendation_assessment_feedback WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.prospects WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 0
        )
        assert connection.execute(
            "SELECT status,current_revision_id FROM operational.recommendations WHERE id=%s",
            (recommendation.id,),
        ).fetchone() == ("open", newest.id)


def test_feedback_cross_company_receipt_conflict_rolls_back_losing_append(
    management_database_url,
):
    identity, first_rec, first_rev = _setup(management_database_url)
    with psycopg.connect(management_database_url) as connection:
        company_id = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Feedback race') RETURNING id",
            (f"{uuid4()}.example.test",),
        ).fetchone()[0]
        _, second_rec, second_rev = seed_owned_recommendation_revision(
            connection, replace(identity, company_id=company_id)
        )
    barrier = Barrier(2, timeout=5)

    class FencedWork(PostgresProspectingUnitOfWork):
        def __enter__(self):
            super().__enter__()
            commands = self.commands

            def record(receipt):
                barrier.wait()
                return commands.record(receipt)

            self.commands = SimpleNamespace(
                get_by_key=commands.get_by_key, record=record
            )
            return self

    def record(pair):
        rec, rev = pair
        request = RecordRecommendationFeedbackRequest(
            rec.id, rev.id, "race-key", RecommendationFeedback("useful")
        )
        try:
            return RecordRecommendationFeedbackService(
                _work(management_database_url, FencedWork)
            ).execute(_principal(identity), request)
        except ConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(record, ((first_rec, first_rev), (second_rec, second_rev)))
        )
    assert sum(result is not None for result in results) == 1
    winner = next(result for result in results if result is not None)
    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT id FROM operational.recommendation_assessment_feedback WHERE business_id=%s",
            (identity.business_id,),
        ).fetchall() == [(winner.feedback.id,)]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert connection.execute(
            "SELECT status FROM operational.recommendations WHERE business_id=%s",
            (identity.business_id,),
        ).fetchall() == [("open",), ("open",)]


def test_feedback_foreign_revision_does_not_write_any_report(management_database_url):
    identity, recommendation, _ = _setup(management_database_url)
    foreign, _, foreign_revision = _setup(management_database_url)
    with pytest.raises(NotFoundError):
        RecordRecommendationFeedbackService(_work(management_database_url)).execute(
            _principal(identity),
            RecordRecommendationFeedbackRequest(
                recommendation.id,
                foreign_revision.id,
                "foreign-revision",
                RecommendationFeedback("useful"),
            ),
        )
    with psycopg.connect(management_database_url) as connection:
        for owner in (identity, foreign):
            assert (
                connection.execute(
                    "SELECT count(*) FROM operational.recommendation_assessment_feedback WHERE business_id=%s",
                    (owner.business_id,),
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM operational.command_receipts WHERE business_id=%s",
                    (owner.business_id,),
                ).fetchone()[0]
                == 0
            )
