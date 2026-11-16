"""Retained-source end-to-end lifecycle and shared-channel races."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event, Lock

import psycopg
import pytest

from huginn.management.application.requests.confirm_recommendation_offer_request import (
    ConfirmRecommendationOfferRequest,
)
from huginn.management.application.requests.generate_recommendations_request import (
    GenerateRecommendationsRequest,
)
from huginn.management.application.requests.prepare_recommendation_offer_request import (
    PrepareRecommendationOfferRequest,
)
from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.recommendation_offer_service import (
    RecommendationOfferService,
)
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.delivery.templates.weekly_digest import (
    PlainTextWeeklyDigestRenderer,
)
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.repositories.digest_subscription_access import (
    PostgresDigestSubscriptionAccess,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)
from huginn.management.persistence.repositories.weekly_digest_content import (
    PostgresWeeklyDigestContentRepository,
)
from huginn.management.persistence.repositories.weekly_digest_delivery import (
    PostgresWeeklyDigestDeliveryRepository,
)
from tests.management.persistence.retained_prospecting_fixtures import (
    seed_retained_brightroom_context,
)
from tests.postgres_harness import provisioned_postgres


@pytest.fixture
def end_to_end_database_url():
    with provisioned_postgres("huginn_prospecting_end_to_end_test") as url:
        with psycopg.connect(url, autocommit=True) as connection:
            for filename in (
                "operational-recommendations.sql",
                "operational-weekly-digest.sql",
                "operational-weekly-digest-content.sql",
            ):
                connection.execute(
                    (Path("db/schema") / filename).read_text(encoding="utf-8")
                )
        yield url


def _subscribe(context):
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "INSERT INTO operational.account_recovery_identity "
            "(account_id,verification_required,verified_email,verified_at) "
            "VALUES (%s,true,%s,%s)",
            (
                context.account_id,
                f"end-to-end-{context.suffix}@example.test",
                context.current_time[0],
            ),
        )
    with PostgresProspectingUnitOfWork(context.connection_factory) as work:
        PostgresDigestSubscriptionAccess(work.connection).subscribe(
            context.owner_user_id, context.business_id, context.current_time[0]
        )
        work.commit()


def _weekly_service(context, sender, generation=None):
    def make_work():
        return PostgresProspectingUnitOfWork(context.connection_factory)

    return WeeklyDigestService(
        make_work,
        subscription_access_factory=lambda work: PostgresDigestSubscriptionAccess(
            work.connection
        ),
        delivery_repository_factory=lambda work: PostgresWeeklyDigestDeliveryRepository(
            work.connection
        ),
        content_repository_factory=lambda work: PostgresWeeklyDigestContentRepository(
            work.connection
        ),
        source_factory=PostgresRecommendationGenerationSource,
        generation=generation or context.generation_service,
        renderer=PlainTextWeeklyDigestRenderer(
            "https://huginn.example", "end-to-end-signing-key", "huginn.example"
        ),
        sender=sender,
        sender_address="weekly@huginn.example",
        clock=lambda: context.current_time[0],
    )


def _offer_services(context):
    def factory():
        return PostgresProspectingUnitOfWork(context.connection_factory)

    prepare = RecommendationOfferService(
        factory,
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: context.current_time[0],
    )
    confirm = RecommendationOfferService(
        factory,
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: context.current_time[0],
    )
    return prepare, confirm


def test_retained_source_fit_change_cooldown_reassessment_renewal_and_exact_save(
    end_to_end_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(end_to_end_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        # The retained source says Germany. The harness's initial US Gold fact
        # is the known-mismatch baseline; NULL lets the captured observation
        # establish the Germany fit without changing the source payload.
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (context.company_id,)
        )
        connection.commit()

    initial = context.generation_service.execute(
        context.principal, GenerateRecommendationsRequest(context.strategy_id)
    )
    assert len(initial.references) == 1
    initial_reference = initial.references[0]
    prepare, confirm = _offer_services(context)
    first_claim = prepare.prepare(
        context.principal,
        PrepareRecommendationOfferRequest(
            initial_reference.recommendation_id,
            initial_reference.revision_id,
            f"retained-initial-offer-{context.suffix}",
        ),
    )
    first_offer = confirm.confirm(
        context.principal,
        ConfirmRecommendationOfferRequest(
            first_claim.offer_cycle_id, first_claim.claim_token
        ),
    )
    assert first_offer.presented_at == context.current_time[0]
    with psycopg.connect(context.database_url) as connection:
        first_recommendation_state = connection.execute(
            "SELECT id,current_revision_id,version,status,first_presented_at "
            "FROM operational.recommendations WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
    assert first_recommendation_state[:2] == (
        initial_reference.recommendation_id,
        initial_reference.revision_id,
    )
    assert first_recommendation_state[2] >= initial_reference.recommendation_version
    assert first_recommendation_state[3:] == ("open", first_offer.presented_at)

    _subscribe(context)
    sent_messages = []

    class Sender:
        def send(self, message):
            sent_messages.append(message)
            return context.current_time[0]

    weekly = _weekly_service(context, Sender())
    context.current_time[0] = first_offer.presented_at + timedelta(days=7)
    week_one = weekly.run()
    assert week_one["sent"] == 0
    assert week_one["empty"] == 1
    assert sent_messages == []

    context.current_time[0] = first_offer.presented_at + timedelta(days=35)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country='US' WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    mismatch_run = context.generation_service.execute(
        context.principal, GenerateRecommendationsRequest(context.strategy_id)
    )
    assert all(
        reference.recommendation_id != initial_reference.recommendation_id
        for reference in mismatch_run.references
    )
    old_view = context.read_service.get_recommendation(
        context.principal,
        initial_reference.recommendation_id,
        assessment_revision_id=initial_reference.revision_id,
    )
    assert old_view.assessment is not None
    assert old_view.assessment.id == initial_reference.revision_id
    assert old_view.company.country == "US"
    assert old_view.evidence_state == "current"
    assert old_view.current_eligibility == "not_reassessed"

    with psycopg.connect(context.database_url) as connection:
        recommendation_before_restore = connection.execute(
            "SELECT id,current_revision_id,version,status,first_presented_at "
            "FROM operational.recommendations WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
        old_revision_snapshot = connection.execute(
            "SELECT to_jsonb(revision) FROM operational.assessment_revisions revision "
            "WHERE id=%s",
            (initial_reference.revision_id,),
        ).fetchone()[0]
        assert recommendation_before_restore == first_recommendation_state
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.assessment_revisions "
                "WHERE recommendation_id=%s",
                (initial_reference.recommendation_id,),
            ).fetchone()[0]
            == 1
        )

        # Restore only the controlled Gold fact. Reassessment still reads the
        # captured, guarded source observation and its original lineage.
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (context.company_id,)
        )
        connection.commit()

    renewed = context.generation_service.execute(
        context.principal, GenerateRecommendationsRequest(context.strategy_id)
    )
    renewed_reference = next(
        reference
        for reference in renewed.references
        if reference.recommendation_id == initial_reference.recommendation_id
    )
    assert renewed_reference.revision_id != initial_reference.revision_id
    with psycopg.connect(context.database_url) as connection:
        current_recommendation = connection.execute(
            "SELECT id,current_revision_id,status,first_presented_at "
            "FROM operational.recommendations WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
        assert current_recommendation == (
            initial_reference.recommendation_id,
            renewed_reference.revision_id,
            "open",
            first_offer.presented_at,
        )
        assert (
            connection.execute(
                "SELECT to_jsonb(revision) FROM operational.assessment_revisions "
                "revision WHERE id=%s",
                (initial_reference.revision_id,),
            ).fetchone()[0]
            == old_revision_snapshot
        )
        new_revision = connection.execute(
            "SELECT to_jsonb(revision) FROM operational.assessment_revisions revision "
            "WHERE id=%s",
            (renewed_reference.revision_id,),
        ).fetchone()[0]
        assert new_revision["evidence_observation_ids"]
        observation_ids = set(new_revision["evidence_observation_ids"])
        evidence_ids = {
            evidence["observation_id"]
            for evidence in new_revision["evidence_snapshots"]
        }
        assert observation_ids == evidence_ids
        company_facts = new_revision["strategy_assessments"][0]["assessment_snapshot"][
            "company_facts"
        ]
        assert company_facts["raw_country"] is None
        assert company_facts["resolved_country"] == "DE"
        assert company_facts["country_evidence_label"] == "Germany"

    renewed_claim = prepare.prepare(
        context.principal,
        PrepareRecommendationOfferRequest(
            renewed_reference.recommendation_id,
            renewed_reference.revision_id,
            f"retained-renewed-offer-{context.suffix}",
        ),
    )
    renewed_offer = confirm.confirm(
        context.principal,
        ConfirmRecommendationOfferRequest(
            renewed_claim.offer_cycle_id, renewed_claim.claim_token
        ),
    )
    assert renewed_offer.presented_at == context.current_time[0]

    saved = SaveRecommendationService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        clock=lambda: context.current_time[0] + timedelta(seconds=1),
    ).execute(
        context.principal,
        SaveRecommendationRequest(
            renewed_reference.recommendation_id,
            renewed_reference.revision_id,
            f"retained-renewed-save-{context.suffix}",
        ),
    )
    assert saved.assessment_revision_id == renewed_reference.revision_id

    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT id,status,current_revision_id,first_presented_at "
            "FROM operational.recommendations WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone() == (
            initial_reference.recommendation_id,
            "converted",
            renewed_reference.revision_id,
            first_offer.presented_at,
        )
        cycles = connection.execute(
            "SELECT id,selected_revision_id,status,presented_at "
            "FROM operational.offer_cycles WHERE business_id=%s AND company_id=%s "
            "ORDER BY created_at,id",
            (context.business_id, context.company_id),
        ).fetchall()
        assert cycles == [
            (
                first_claim.offer_cycle_id,
                initial_reference.revision_id,
                "confirmed",
                first_offer.presented_at,
            ),
            (
                renewed_claim.offer_cycle_id,
                renewed_reference.revision_id,
                "confirmed",
                renewed_offer.presented_at,
            ),
        ]
        assert connection.execute(
            "SELECT recommendation_id,assessment_revision_id FROM operational.prospect_origins "
            "WHERE id=%s",
            (saved.origin_id,),
        ).fetchone() == (
            renewed_reference.recommendation_id,
            renewed_reference.revision_id,
        )
        assert (
            connection.execute(
                "SELECT id,username,status FROM operational.accounts WHERE id=%s",
                (context.account_id,),
            ).fetchone()
            == context.account_before
        )
        assert (
            connection.execute(
                "SELECT to_jsonb(profile) FROM operational.professional_profiles profile "
                "WHERE user_id=%s",
                (context.owner_user_id,),
            ).fetchone()[0]
            == context.personal_profile_before
        )
        assert (
            connection.execute(
                "SELECT business_id,repeat_interval_days,updated_at "
                "FROM operational.business_recommendation_preferences WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()
            == context.preferences_before
        )
        configuration_after = connection.execute(
            "SELECT s.id,s.service_offering_id,s.ideal_client_profile_id,o.name,o.description,"
            "i.name,i.geographies FROM operational.client_discovery_strategies s "
            "JOIN operational.service_offerings o ON o.id=s.service_offering_id "
            "JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id "
            "WHERE s.business_id=%s ORDER BY s.id",
            (context.business_id,),
        ).fetchall()
        assert configuration_after == context.configuration_before
        with PostgresProspectingUnitOfWork(
            context.connection_factory, read_only=True
        ) as work:
            current_source = PostgresRecommendationGenerationSource(work.connection)
            saved_revision = work.assessment_revisions.get_owned(
                context.business_id,
                renewed_reference.recommendation_id,
                renewed_reference.revision_id,
            )
            assert (
                current_source.current_company_for_revision(
                    saved_revision, context.current_time[0]
                )
                is not None
            )


def test_retained_company_multistrategy_email_save_and_origin_keep_both_snapshots(
    end_to_end_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(end_to_end_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (context.company_id,)
        )
        connection.commit()
    _subscribe(context)

    messages = []

    class Sender:
        def send(self, message):
            messages.append(message)
            return context.current_time[0]

    result = _weekly_service(context, Sender()).run()
    assert result["sent"] == 1
    assert len(messages) == 1
    assert messages[0].body.count("Review this recommendation:") == 1
    assert messages[0].body.count("Strategy relevance:") == 2

    with psycopg.connect(context.database_url) as connection:
        members = connection.execute(
            "SELECT member.company_id,member.recommendation_id,"
            "member.assessment_revision_id,member.offer_cycle_id,member.position "
            "FROM operational.weekly_digest_members member "
            "JOIN operational.weekly_digest_deliveries delivery "
            "ON delivery.id=member.delivery_id "
            "WHERE delivery.business_id=%s",
            (context.business_id,),
        ).fetchall()
        assert len(members) == 1
        member = members[0]
        assert member[0] == context.company_id
        assert member[4] == 1
        revision_before_save = connection.execute(
            "SELECT to_jsonb(revision) FROM operational.assessment_revisions revision "
            "WHERE id=%s",
            (member[2],),
        ).fetchone()[0]
        associations = revision_before_save["strategy_assessments"]
        assert {value["strategy_id"] for value in associations} == {
            str(context.strategy_id),
            str(context.second_strategy_id),
        }
        assert len(associations) == 2
        retained_scores = sorted(
            value["assessment_snapshot"]["score"] for value in associations
        )
        email_scores = sorted(
            int(line.split(": ", 1)[1].split("/", 1)[0])
            for line in messages[0].body.splitlines()
            if line.startswith("Strategy relevance:")
        )
        assert email_scores == retained_scores

    saved = SaveRecommendationService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        clock=lambda: context.current_time[0] + timedelta(seconds=1),
    ).execute(
        context.principal,
        SaveRecommendationRequest(
            member[1], member[2], f"multistrategy-save-{context.suffix}"
        ),
    )
    prospect = context.read_service.get_prospect(context.principal, saved.prospect_id)
    assert len(prospect.origins) == 1
    origin_view = prospect.origins[0]
    assert origin_view.origin.id == saved.origin_id
    assert origin_view.origin.recommendation_id == member[1]
    assert origin_view.origin.assessment_revision_id == member[2]
    assert origin_view.assessment.id == member[2]
    assert len(origin_view.assessment.strategy_assessments) == 2
    assert {
        value.strategy_id for value in origin_view.assessment.strategy_assessments
    } == {context.strategy_id, context.second_strategy_id}
    assert (
        sorted(
            value.assessment_snapshot.to_json_object()["score"]
            for value in origin_view.assessment.strategy_assessments
        )
        == retained_scores
    )

    with psycopg.connect(context.database_url) as connection:
        revision_after_save = connection.execute(
            "SELECT to_jsonb(revision) FROM operational.assessment_revisions revision "
            "WHERE id=%s",
            (member[2],),
        ).fetchone()[0]
        assert revision_after_save == revision_before_save
        persisted_origin = connection.execute(
            "SELECT recommendation_id,assessment_revision_id,company_id "
            "FROM operational.prospect_origins WHERE id=%s",
            (saved.origin_id,),
        ).fetchone()
        assert persisted_origin == (member[1], member[2], context.company_id)


def test_two_weekly_workers_reserve_one_delivery_and_send_once(
    end_to_end_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(end_to_end_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (context.company_id,)
        )
        connection.commit()
    _subscribe(context)
    sent_messages = []
    sent_lock = Lock()

    class Sender:
        def send(self, message):
            with sent_lock:
                sent_messages.append(message)
            return context.current_time[0]

    services = (_weekly_service(context, Sender()), _weekly_service(context, Sender()))
    start = Barrier(2)

    def run_together(service):
        start.wait(timeout=5)
        return service.run()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_together, services))

    assert sum(result["sent"] for result in results) == 1
    assert len(sent_messages) == 1
    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT state,count(*) FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s GROUP BY state",
            (context.business_id,),
        ).fetchall() == [("sent", 1)]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_contents "
                "WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycles "
                "WHERE business_id=%s AND company_id=%s AND status='confirmed'",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendations "
                "WHERE business_id=%s AND company_id=%s",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 1
        )


def test_app_prepare_wins_while_weekly_generation_is_in_flight(
    end_to_end_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(end_to_end_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (context.company_id,)
        )
        connection.commit()
    _subscribe(context)
    committed_weekly_selection = context.generation_service.execute_weekly(
        context.business_id
    )
    assert len(committed_weekly_selection.references) == 1
    selected_reference = committed_weekly_selection.references[0]
    generation_selected = Event()
    continue_weekly = Event()

    class SelectedCommittedGeneration:
        def execute_weekly(self, business_id):
            assert business_id == context.business_id
            generation_selected.set()
            if not continue_weekly.wait(timeout=10):
                raise TimeoutError("App preparation did not finish during weekly run")
            return committed_weekly_selection

    sent_messages = []

    class Sender:
        def send(self, message):
            sent_messages.append(message)
            return context.current_time[0]

    weekly = _weekly_service(
        context, Sender(), generation=SelectedCommittedGeneration()
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        weekly_future = pool.submit(weekly.run)
        assert generation_selected.wait(timeout=10)
        prepare, confirm = _offer_services(context)
        app_claim = prepare.prepare(
            context.principal,
            PrepareRecommendationOfferRequest(
                selected_reference.recommendation_id,
                selected_reference.revision_id,
                f"app-during-weekly-{context.suffix}",
            ),
        )
        continue_weekly.set()
        weekly_result = weekly_future.result(timeout=20)

    assert weekly_result["sent"] == 0
    assert weekly_result["skipped"] == 1
    assert sent_messages == []
    app_offer = confirm.confirm(
        context.principal,
        ConfirmRecommendationOfferRequest(
            app_claim.offer_cycle_id, app_claim.claim_token
        ),
    )
    assert app_offer.presented_at == context.current_time[0]

    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT id,current_revision_id,status,first_presented_at "
            "FROM operational.recommendations WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone() == (
            selected_reference.recommendation_id,
            selected_reference.revision_id,
            "open",
            app_offer.presented_at,
        )
        assert connection.execute(
            "SELECT id,selected_revision_id,status,presented_at "
            "FROM operational.offer_cycles WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchall() == [
            (
                app_claim.offer_cycle_id,
                selected_reference.revision_id,
                "confirmed",
                app_offer.presented_at,
            )
        ]
        assert connection.execute(
            "SELECT state FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s",
            (context.business_id,),
        ).fetchall() == [("suppressed",)]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_contents "
                "WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == 0
        )
