from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.errors.mail_pre_transport import (
    MailPreTransportError,
)
from huginn.management.application.policies.recommendation_profile_validation import (
    validated_profile_inputs,
)
from huginn.management.application.requests.later_recommendation_request import (
    LaterRecommendationRequest,
)
from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.application.requests.prepare_recommendation_offer_request import (
    PrepareRecommendationOfferRequest,
)
from huginn.management.application.requests.reconcile_stopped_weekly_digest_request import (
    ReconcileStoppedWeeklyDigestRequest,
)
from huginn.management.application.requests.record_recommendation_feedback_request import (
    RecordRecommendationFeedbackRequest,
)
from huginn.management.application.requests.recover_weekly_digest_request import (
    RecoverWeeklyDigestRequest,
)
from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.recommendation_decision_service import (
    RecommendationDecisionService,
)
from huginn.management.application.services.recommendation_offer_service import (
    RecommendationOfferService,
)
from huginn.management.application.services.record_recommendation_feedback_service import (
    RecordRecommendationFeedbackService,
)
from huginn.management.application.services.recover_weekly_digest_service import (
    RecoverWeeklyDigestService,
)
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.delivery.templates.weekly_digest import (
    PlainTextWeeklyDigestRenderer,
)
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.pause_choice import PauseChoice
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.persistence.database.client import ManagementConnectionFactory
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
def weekly_service_database_url():
    with provisioned_postgres("huginn_weekly_digest_service_test") as url:
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
                f"weekly-{context.suffix}@example.test",
                context.current_time[0],
            ),
        )
    with PostgresProspectingUnitOfWork(context.connection_factory) as work:
        PostgresDigestSubscriptionAccess(work.connection).subscribe(
            context.owner_user_id, context.business_id, context.current_time[0]
        )
        work.commit()


def _assert_no_open_transactions(database_url):
    with psycopg.connect(database_url) as observer:
        assert (
            observer.execute(
                "SELECT pid FROM pg_stat_activity "
                "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                "AND backend_type='client backend' AND xact_start IS NOT NULL"
            ).fetchall()
            == []
        )


def test_transport_transaction_probe_detects_an_actual_open_uow(
    weekly_service_database_url,
):
    with PostgresProspectingUnitOfWork(
        ManagementConnectionFactory(weekly_service_database_url)
    ) as work:
        work.connection.execute("SELECT 1")
        with pytest.raises(AssertionError):
            _assert_no_open_transactions(weekly_service_database_url)
    _assert_no_open_transactions(weekly_service_database_url)


def _make_service(context, sender, renderer=None, generation=None):
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
        renderer=renderer
        or PlainTextWeeklyDigestRenderer(
            "https://huginn.example", "weekly-test-signing-key", "huginn.example"
        ),
        sender=sender,
        sender_address="weekly@huginn.example",
        clock=lambda: context.current_time[0],
    )


def test_weekly_publication_commits_only_final_content_and_sending_claims(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
    _subscribe(context)
    before_authorization = {}

    class Sender:
        def send(self, message):
            _assert_no_open_transactions(context.database_url)
            with psycopg.connect(context.database_url) as connection:
                assert connection.execute(
                    "SELECT state FROM operational.weekly_digest_deliveries "
                    "WHERE business_id=%s",
                    (context.business_id,),
                ).fetchall() == [("sending",)]
                assert connection.execute(
                    "SELECT status FROM operational.offer_cycles WHERE business_id=%s",
                    (context.business_id,),
                ).fetchall() == [("sending",)]
            return context.current_time[0]

    service = _make_service(context, Sender())
    base_authorize = service._authorize

    def authorize_without_prepared_writes(*args):
        with psycopg.connect(context.database_url) as connection:
            before_authorization["cycles"] = connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE business_id=%s",
                (context.business_id,),
            ).fetchall()
            before_authorization["contents"] = connection.execute(
                "SELECT id FROM operational.weekly_digest_contents WHERE business_id=%s",
                (context.business_id,),
            ).fetchall()
        return base_authorize(*args)

    service._authorize = authorize_without_prepared_writes
    assert service.run()["sent"] == 1
    assert before_authorization == {"cycles": [], "contents": []}
    with psycopg.connect(context.database_url) as connection:
        rows = connection.execute(
            "SELECT c.version,m.recommendation_id,m.assessment_revision_id,"
            "cycle.selected_revision_id,r.current_revision_id "
            "FROM operational.weekly_digest_contents c "
            "JOIN operational.weekly_digest_members m ON m.content_id=c.id "
            "JOIN operational.offer_cycles cycle ON cycle.id=m.offer_cycle_id "
            "JOIN operational.recommendations r ON r.id=m.recommendation_id "
            "WHERE c.business_id=%s",
            (context.business_id,),
        ).fetchall()
        assert len(rows) == 1
        (
            content_version,
            recommendation_id,
            member_revision,
            cycle_revision,
            current_revision,
        ) = rows[0]
        assert content_version == 1
        assert recommendation_id is not None
        assert member_revision == cycle_revision == current_revision


def test_render_failure_rolls_back_publication_without_losing_generated_assessment(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
    _subscribe(context)

    class Renderer:
        def render(self, subscription, week_start, content_id, revisions):
            assert len(revisions) == 1
            raise RuntimeError("Rendering failed before publication")

    class Sender:
        def send(self, message):
            raise AssertionError("Unpublished content must not reach SMTP")

    assert _make_service(context, Sender(), Renderer()).run()["failed"] == 1
    _assert_no_open_transactions(context.database_url)
    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT state,current_content_id FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s",
            (context.business_id,),
        ).fetchall() == [("failed", None)]
        for table in (
            "weekly_digest_contents",
            "offer_cycles",
            "offer_cycle_events",
            "suppression_blocks",
        ):
            assert connection.execute(
                f"SELECT count(*) FROM operational.{table} WHERE business_id=%s",
                (context.business_id,),
            ).fetchone() == (0,)
        revision = connection.execute(
            "SELECT r.current_revision_id,a.id,r.first_presented_at "
            "FROM operational.recommendations r "
            "JOIN operational.assessment_revisions a ON a.id=r.current_revision_id "
            "WHERE r.business_id=%s AND r.company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
        assert revision is not None
        assert revision[0] == revision[1]
        assert revision[2] is None


def test_retained_source_weekly_delivery_respects_full_cooldown_and_renews_after_day35(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)

    sent_messages = []

    class Sender:
        def send(self, message):
            sent_messages.append(message)
            return context.current_time[0]

    service = _make_service(context, Sender())

    first = service.run()
    assert first == {
        "eligible": 1,
        "sent": 1,
        "skipped": 0,
        "empty": 0,
        "unknown": 0,
        "failed": 0,
    }
    assert len(sent_messages) == 1
    assert "Brightroom" in sent_messages[0].body
    assert "/recommendations?recommendation_id=" in sent_messages[0].body
    assert "batch=" not in sent_messages[0].body

    for _day in (7, 14, 21, 28):
        context.current_time[0] += timedelta(days=7)
        result = service.run()
        assert result["sent"] == 0
        assert result["empty"] == 1
        assert len(sent_messages) == 1

    first_delivery_at = context.current_time[0] - timedelta(days=28)
    with psycopg.connect(context.database_url) as connection:
        delivery_rows = connection.execute(
            "SELECT id,state,accepted_at FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s ORDER BY week_start",
            (context.business_id,),
        ).fetchall()
        assert len(delivery_rows) == 5
        assert delivery_rows[0][1:] == ("sent", first_delivery_at)
        assert all(row[1] == "empty" for row in delivery_rows[1:])
        initial_presentation = connection.execute(
            "SELECT first_presented_at FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()[0]
        first_cycle = connection.execute(
            "SELECT id,selected_revision_id,status FROM operational.offer_cycles "
            "WHERE business_id=%s AND company_id=%s AND status='confirmed'",
            (context.business_id, context.company_id),
        ).fetchone()
        initial_cooldown = connection.execute(
            "SELECT effective_at,expires_at FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
            (context.business_id, context.company_id),
        ).fetchone()
        assert first_cycle is not None
        assert initial_presentation == first_delivery_at
        assert initial_cooldown == (
            first_delivery_at,
            first_delivery_at + timedelta(days=30),
        )

    context.current_time[0] += timedelta(days=7)
    day35 = service.run()
    assert day35["sent"] == 1
    assert len(sent_messages) == 2

    with psycopg.connect(context.database_url) as connection:
        cycles = connection.execute(
            "SELECT id,selected_revision_id,status,presented_at FROM operational.offer_cycles "
            "WHERE business_id=%s AND company_id=%s AND status='confirmed' "
            "ORDER BY created_at,id",
            (context.business_id, context.company_id),
        ).fetchall()
        assert len(cycles) == 2
        assert cycles[0][2:] == ("confirmed", first_delivery_at)
        assert cycles[1][1] != cycles[0][1]
        assert cycles[1][3] == context.current_time[0]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_contents c "
                "JOIN operational.weekly_digest_members m ON m.content_id=c.id "
                "WHERE c.business_id=%s AND m.company_id=%s",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendation_batches WHERE user_id=%s",
                (context.owner_user_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT first_presented_at FROM operational.recommendations "
                "WHERE business_id=%s AND company_id=%s",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == initial_presentation
        )


def test_retained_source_changed_offering_creates_fresh_revision_without_rewriting_old_email_or_feedback(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)
    messages = []

    class Sender:
        def send(self, message):
            messages.append(message)
            return context.current_time[0]

    service = _make_service(context, Sender())
    assert service.run()["sent"] == 1
    with psycopg.connect(context.database_url) as connection:
        original = connection.execute(
            "SELECT m.recommendation_id,m.assessment_revision_id,c.id,c.body "
            "FROM operational.weekly_digest_contents c "
            "JOIN operational.weekly_digest_members m ON m.content_id=c.id "
            "WHERE c.business_id=%s",
            (context.business_id,),
        ).fetchone()
        old_revision = connection.execute(
            "SELECT to_jsonb(revision) FROM operational.assessment_revisions revision "
            "WHERE id=%s",
            (original[1],),
        ).fetchone()[0]
        old_association = old_revision["strategy_assessments"][0]
        old_rationale = old_association["assessment_snapshot"]["rationale"]
        original_offering = connection.execute(
            "SELECT id,description FROM operational.service_offerings WHERE id=%s",
            (old_association["offering_id"],),
        ).fetchone()
        assert original_offering is not None
        connection.commit()

    report_feedback = RecordRecommendationFeedbackService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory)
    )
    feedback_request = RecordRecommendationFeedbackRequest(
        original[0],
        original[1],
        f"weekly-feedback-{context.suffix}",
        RecommendationFeedback("useful", notes="The original offer was relevant"),
    )
    feedback = report_feedback.execute(context.principal, feedback_request).feedback

    changed_description = "Career coaching marketplace for independent founders"
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE operational.service_offerings SET description=%s WHERE id=%s",
            (changed_description, original_offering[0]),
        )
        connection.commit()
    context.current_time[0] += timedelta(days=35)

    assert service.run()["sent"] == 1
    assert len(messages) == 2
    with psycopg.connect(context.database_url) as connection:
        rec = connection.execute(
            "SELECT current_revision_id FROM operational.recommendations WHERE id=%s",
            (original[0],),
        ).fetchone()[0]
        assert rec != original[1]
        new_revision = connection.execute(
            "SELECT to_jsonb(revision) FROM operational.assessment_revisions revision "
            "WHERE id=%s AND recommendation_id=%s",
            (rec, original[0]),
        ).fetchone()[0]
        changed_association = next(
            item
            for item in new_revision["strategy_assessments"]
            if item["offering_id"] == str(original_offering[0])
        )
        assert changed_association["offering_snapshot"]["description"] == (
            changed_description
        )
        # The first email and its evidence remain the exact historical view.
        assert len(messages[0].body) > 0
        first_content = connection.execute(
            "SELECT body FROM operational.weekly_digest_contents WHERE id=%s",
            (original[2],),
        ).fetchone()[0]
        assert first_content == original[3]
        assert first_content == messages[0].body
        assert "Career coaching marketplace" not in first_content
        assert (
            connection.execute(
                "SELECT to_jsonb(revision) FROM operational.assessment_revisions revision "
                "WHERE id=%s",
                (original[1],),
            ).fetchone()[0]
            == old_revision
        )
        assert connection.execute(
            "SELECT recommendation_id,assessment_revision_id,company_id,position "
            "FROM operational.weekly_digest_members WHERE content_id=%s",
            (original[2],),
        ).fetchone() == (original[0], original[1], context.company_id, 1)
        assert connection.execute(
            "SELECT assessment_revision_id,payload FROM operational.recommendation_assessment_feedback "
            "WHERE id=%s",
            (feedback.id,),
        ).fetchone() == (
            original[1],
            {
                "usefulness": "useful",
                "reasons": [],
                "correction": "",
                "next_step": "none",
                "outcome": "unknown",
                "notes": "The original offer was relevant",
            },
        )
        second_content = connection.execute(
            "SELECT c.body,m.assessment_revision_id FROM operational.weekly_digest_contents c "
            "JOIN operational.weekly_digest_members m ON m.content_id=c.id "
            "WHERE c.business_id=%s ORDER BY c.created_at DESC LIMIT 1",
            (context.business_id,),
        ).fetchone()
        assert second_content[1] == rec
        assert second_content[0] == messages[1].body
        assert second_content[0] != first_content
        assert f"assessment_revision_id={rec}" in second_content[0]

    # Saving the old shown revision after renewal must keep the origin on that
    # exact revision rather than silently upgrading it to the current pointer.
    saved = SaveRecommendationService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        clock=lambda: context.current_time[0] + timedelta(seconds=1),
    ).execute(
        context.principal,
        SaveRecommendationRequest(
            original[0], original[1], f"weekly-save-old-{context.suffix}"
        ),
    )
    assert saved.assessment_revision_id == original[1]
    with psycopg.connect(context.database_url) as connection:
        origin = connection.execute(
            "SELECT recommendation_id,assessment_revision_id FROM operational.prospect_origins "
            "WHERE id=%s",
            (saved.origin_id,),
        ).fetchone()
        assert origin == (original[0], original[1])
        assert (
            connection.execute(
                "SELECT strategy_assessments FROM operational.assessment_revisions WHERE id=%s",
                (original[1],),
            ).fetchone()[0][0]["assessment_snapshot"]["rationale"]
            == old_rationale
        )


def test_unknown_weekly_delivery_recovers_with_actual_handoff_and_frozen_cadence(
    weekly_service_database_url, monkeypatch
):

    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)

    class UnknownSender:
        def send(self, message):
            raise OSError("Connection lost after SMTP handoff")

    service = _make_service(context, UnknownSender())
    result = service.run()
    assert result["unknown"] == 1
    with psycopg.connect(context.database_url) as connection:
        delivery = connection.execute(
            "SELECT id,state,version,current_content_id FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s",
            (context.business_id,),
        ).fetchone()
        assert delivery[1] == "unknown"
        cycle = connection.execute(
            "SELECT id,company_id,sending_started_at,status FROM operational.offer_cycles "
            "WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
        assert cycle[3] == "unknown"
        member = connection.execute(
            "SELECT recommendation_id,assessment_revision_id,offer_cycle_id "
            "FROM operational.weekly_digest_members WHERE content_id=%s",
            (delivery[3],),
        ).fetchone()
        assert member[2] == cycle[0]
        actual_accepted = cycle[2] + timedelta(seconds=10)
        connection.execute(
            "UPDATE operational.business_recommendation_preferences "
            "SET repeat_interval_days=60,updated_at=updated_at+interval '1 second' "
            "WHERE business_id=%s",
            (context.business_id,),
        )
        connection.commit()

    context.current_time[0] = cycle[2] + timedelta(days=35)
    day35 = context.current_time[0]
    day35_week = day35.date() - timedelta(days=day35.weekday())
    day_start = datetime.combine(day35.date(), time.min, UTC)
    with PostgresProspectingUnitOfWork(context.connection_factory) as work:
        source = PostgresRecommendationGenerationSource(work.connection)
        active_profiles = source.active_profiles(context.owner_user_id)
        valid_profiles = []
        for profile in active_profiles:
            try:
                validated_profile_inputs(profile)
            except Exception:
                continue
            valid_profiles.append(profile)
        state_at_day35 = source.company_states(
            context.business_id, (context.company_id,), day35
        )[0]
    with psycopg.connect(context.database_url) as connection:
        same_week_reservation = connection.execute(
            "SELECT count(*) FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s AND week_start=%s",
            (context.business_id, day35_week),
        ).fetchone()[0]
        same_day_reservations = connection.execute(
            "SELECT count(*) FROM operational.weekly_digest_deliveries "
            "WHERE created_at >= %s AND created_at < %s",
            (day_start, day_start + timedelta(days=1)),
        ).fetchone()[0]
    with psycopg.connect(context.database_url) as connection:
        current_before = connection.execute(
            "SELECT current_revision_id FROM operational.recommendations WHERE id=%s",
            (member[0],),
        ).fetchone()[0]
        revision_count_before = connection.execute(
            "SELECT count(*) FROM operational.assessment_revisions "
            "WHERE recommendation_id=%s",
            (member[0],),
        ).fetchone()[0]
    assert state_at_day35.uncertain_delivery is True
    assert state_at_day35.pending_delivery is False
    day35_generation = context.generation_service.execute_weekly(context.business_id)
    assert day35_generation.references == ()
    retry_after_unknown = service.run()
    assert retry_after_unknown["sent"] == 0
    assert retry_after_unknown["empty"] + retry_after_unknown["skipped"] == 1
    assert state_at_day35.uncertain_delivery
    if retry_after_unknown["skipped"]:
        assert (
            not valid_profiles or same_week_reservation or same_day_reservations >= 100
        ), {
            "valid_active_profiles": len(valid_profiles),
            "same_week_reservation": same_week_reservation,
            "same_day_reservations": same_day_reservations,
        }
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE id=%s",
                (delivery[0],),
            ).fetchone()[0]
            == "unknown"
        )
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE id=%s",
                (cycle[0],),
            ).fetchone()[0]
            == "unknown"
        )
        assert (
            connection.execute(
                "SELECT first_presented_at FROM operational.recommendations WHERE id=%s",
                (member[0],),
            ).fetchone()[0]
            is None
        )
        weekly_delivery_states = connection.execute(
            "SELECT state FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s ORDER BY week_start",
            (context.business_id,),
        ).fetchall()
        assert weekly_delivery_states[0] == ("unknown",)
        assert len(weekly_delivery_states) <= 2
        assert all(
            state[0] in {"unknown", "empty", "suppressed"}
            for state in weekly_delivery_states
        )
        assert (
            connection.execute(
                "SELECT current_revision_id FROM operational.recommendations WHERE id=%s",
                (member[0],),
            ).fetchone()[0]
            == current_before
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.assessment_revisions "
                "WHERE recommendation_id=%s",
                (member[0],),
            ).fetchone()[0]
            == revision_count_before
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_contents "
                "WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == 1
        )

    context.current_time[0] += timedelta(minutes=20)
    recover = RecoverWeeklyDigestService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        delivery_repository_factory=lambda work: PostgresWeeklyDigestDeliveryRepository(
            work.connection
        ),
        content_repository_factory=lambda work: PostgresWeeklyDigestContentRepository(
            work.connection
        ),
        clock=lambda: context.current_time[0],
    )
    request = RecoverWeeklyDigestRequest(
        delivery[0],
        "  Confirmed recipient accepted the weekly message  ",
        "sent",
        actual_accepted,
    )
    recovered = recover.execute(context.principal, request)
    assert recovered.state == "sent"
    assert recovered.accepted_at == actual_accepted
    replay = recover.execute(
        context.principal,
        RecoverWeeklyDigestRequest(
            delivery[0],
            "Confirmed recipient accepted the weekly message",
            "sent",
            actual_accepted,
        ),
    )
    assert replay == recovered

    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT status,presented_at FROM operational.offer_cycles WHERE id=%s",
            (cycle[0],),
        ).fetchone() == ("confirmed", actual_accepted)
        assert (
            connection.execute(
                "SELECT first_presented_at FROM operational.recommendations WHERE id=%s",
                (member[0],),
            ).fetchone()[0]
            == actual_accepted
        )
        assert connection.execute(
            "SELECT effective_at,expires_at FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
            (context.business_id, context.company_id),
        ).fetchone() == (
            actual_accepted,
            actual_accepted + timedelta(days=30),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_delivery_events "
                "WHERE delivery_id=%s AND event_kind='unknown_resolved'",
                (delivery[0],),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT reason FROM operational.weekly_digest_delivery_events "
                "WHERE delivery_id=%s AND event_kind='unknown_resolved'",
                (delivery[0],),
            ).fetchone()[0]
            == "Confirmed recipient accepted the weekly message"
        )


@pytest.mark.parametrize("decision", ["save", "not_relevant", "later"])
def test_owner_decision_after_generation_suppresses_weekly_authorization(
    weekly_service_database_url, monkeypatch, decision
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)

    class Sender:
        def send(self, message):
            raise AssertionError("A committed owner decision must suppress SMTP")

    service = _make_service(context, Sender())
    base_authorize = service._authorize
    interposed = False
    selected_reference = None

    def authorize_after_owner_command(subscription, delivery, week_start, references):
        nonlocal interposed, selected_reference
        assert not interposed
        interposed = True
        member = references[0]
        selected_reference = member
        with PostgresProspectingUnitOfWork(context.connection_factory) as work:
            recommendation = work.recommendations.get_owned(
                context.business_id, member.recommendation_id
            )
            preferences = work.business_recommendation_preferences.get(
                context.business_id
            )
            assert recommendation is not None
            assert preferences is not None
            work.commit()

        if decision == "save":
            SaveRecommendationService(
                lambda: PostgresProspectingUnitOfWork(context.connection_factory),
                clock=lambda: context.current_time[0] + timedelta(seconds=1),
            ).execute(
                context.principal,
                SaveRecommendationRequest(
                    member.recommendation_id,
                    member.revision_id,
                    f"save-before-weekly-auth-{context.suffix}",
                ),
            )
        elif decision == "not_relevant":
            RecommendationDecisionService(
                lambda: PostgresProspectingUnitOfWork(context.connection_factory),
                clock=lambda: context.current_time[0] + timedelta(seconds=1),
            ).mark_not_relevant(
                context.principal,
                MarkRecommendationNotRelevantRequest(
                    member.recommendation_id,
                    member.revision_id,
                    recommendation.version,
                    f"reject-before-weekly-auth-{context.suffix}",
                    "Changed before send authorization",
                ),
            )
        else:
            RecommendationDecisionService(
                lambda: PostgresProspectingUnitOfWork(context.connection_factory),
                clock=lambda: context.current_time[0] + timedelta(seconds=1),
            ).later(
                context.principal,
                LaterRecommendationRequest(
                    member.recommendation_id,
                    member.revision_id,
                    recommendation.version,
                    PauseChoice("x1"),
                    preferences.repeat_interval_days,
                    preferences.updated_at,
                    None,
                    None,
                    f"pause-before-weekly-auth-{context.suffix}",
                ),
            )
        context.current_time[0] += timedelta(seconds=2)
        return base_authorize(subscription, delivery, week_start, references)

    service._authorize = authorize_after_owner_command
    result = service.run()
    assert interposed
    assert result["skipped"] == 1
    assert result["sent"] == 0
    assert selected_reference is not None

    with psycopg.connect(context.database_url) as connection:
        recommendation = connection.execute(
            "SELECT id,status,first_presented_at FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
        assert recommendation[2] is None
        assert (
            recommendation[1]
            == {
                "save": "converted",
                "not_relevant": "rejected",
                "later": "open",
            }[decision]
        )
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == "suppressed"
        )
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE business_id=%s",
                (context.business_id,),
            ).fetchall()
            == []
        )
        block_kinds = tuple(
            row[0]
            for row in connection.execute(
                "SELECT kind FROM operational.suppression_blocks "
                "WHERE business_id=%s ORDER BY kind",
                (context.business_id,),
            ).fetchall()
        )
        assert (
            block_kinds
            == {
                "save": (),
                "not_relevant": ("rejection",),
                "later": ("pause",),
            }[decision]
        )

    view = context.read_service.get_recommendation(
        context.principal,
        recommendation[0],
        assessment_revision_id=selected_reference.revision_id,
    )
    assert view.recommendation.status.value == recommendation[1]
    assert view.assessment is not None
    assert view.assessment.id == selected_reference.revision_id
    assert view.recommendation.first_presented_at is None


def test_weekly_sending_claim_suppresses_generation_and_conflicts_with_app_prepare(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)
    sent_messages = []

    class Sender:
        def send(self, message):
            sent_messages.append(message)
            return context.current_time[0]

    service = _make_service(context, Sender())
    base_authorize = service._authorize
    checked = False

    def verify_sending_conflicts(subscription, delivery, week_start, references):
        nonlocal checked
        assert not checked
        checked = True
        authorized = base_authorize(subscription, delivery, week_start, references)
        assert authorized is not None
        _, content, _ = authorized
        member = content.members[0]
        with psycopg.connect(context.database_url) as connection:
            before_revisions = connection.execute(
                "SELECT count(*) FROM operational.assessment_revisions "
                "WHERE recommendation_id=%s",
                (member.recommendation_id,),
            ).fetchone()[0]

        generated = context.generation_service.execute_weekly(context.business_id)
        assert generated.references == ()
        with psycopg.connect(context.database_url) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM operational.assessment_revisions "
                    "WHERE recommendation_id=%s",
                    (member.recommendation_id,),
                ).fetchone()[0]
                == before_revisions
            )
            assert connection.execute(
                "SELECT status FROM operational.offer_cycles "
                "WHERE business_id=%s AND company_id=%s",
                (context.business_id, member.company_id),
            ).fetchall() == [("sending",)]

        prepare = RecommendationOfferService(
            lambda: PostgresProspectingUnitOfWork(context.connection_factory),
            source_factory=PostgresRecommendationGenerationSource,
            clock=lambda: context.current_time[0],
        )
        with pytest.raises(ConflictError):
            prepare.prepare(
                context.principal,
                PrepareRecommendationOfferRequest(
                    member.recommendation_id,
                    member.assessment_revision_id,
                    f"owner-prepare-during-weekly-{context.suffix}",
                ),
            )

        view = context.read_service.get_recommendation(
            context.principal,
            member.recommendation_id,
            assessment_revision_id=member.assessment_revision_id,
        )
        assert view.assessment is not None
        assert view.assessment.id == member.assessment_revision_id
        assert view.recommendation.status.value == "open"
        return authorized

    service._authorize = verify_sending_conflicts
    result = service.run()
    assert checked
    assert result["sent"] == 1
    assert len(sent_messages) == 1
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycles "
                "WHERE business_id=%s AND company_id=%s",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles "
                "WHERE business_id=%s AND company_id=%s",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == "confirmed"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_contents "
                "WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == 1
        )


def test_opt_out_before_authorization_creates_no_claim_or_content(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)

    class Sender:
        def __init__(self):
            self.called = False

        def send(self, message):
            self.called = True
            raise AssertionError("Opt-out before authorization must suppress send")

    sender = Sender()
    service = _make_service(context, sender)
    base_authorize = service._authorize

    def authorize_after_opt_out(*args):
        context.current_time[0] += timedelta(seconds=2)
        with PostgresProspectingUnitOfWork(context.connection_factory) as work:
            PostgresDigestSubscriptionAccess(work.connection).unsubscribe(
                context.owner_user_id, context.business_id, context.current_time[0]
            )
            work.commit()
        return base_authorize(*args)

    service._authorize = authorize_after_opt_out
    result = service.run()
    assert result["skipped"] == 1
    assert not sender.called
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == "suppressed"
        )
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE business_id=%s",
                (context.business_id,),
            ).fetchall()
            == []
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycle_events "
                "WHERE business_id=%s AND event_kind='preparing_abandoned' AND actor_user_id IS NULL",
                (context.business_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND kind='cooldown'",
                (context.business_id,),
            ).fetchone()[0]
            == 0
        )


def test_post_authorization_rejection_and_opt_out_do_not_recall_accepted_message(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)
    sent_messages = []
    rejection_at = context.current_time[0] + timedelta(seconds=1)
    actual_acceptance = context.current_time[0] + timedelta(seconds=3)

    class OptOutAfterAuthorizationSender:
        def send(self, message):
            sent_messages.append(message)
            _assert_no_open_transactions(context.database_url)
            with psycopg.connect(context.database_url) as connection:
                recommendation = connection.execute(
                    "SELECT r.id,r.version,m.assessment_revision_id "
                    "FROM operational.recommendations r "
                    "JOIN operational.weekly_digest_members m "
                    "ON m.recommendation_id=r.id "
                    "JOIN operational.weekly_digest_contents c ON c.id=m.content_id "
                    "WHERE c.business_id=%s",
                    (context.business_id,),
                ).fetchone()
            RecommendationDecisionService(
                lambda: PostgresProspectingUnitOfWork(context.connection_factory),
                clock=lambda: rejection_at,
            ).mark_not_relevant(
                context.principal,
                MarkRecommendationNotRelevantRequest(
                    recommendation[0],
                    recommendation[2],
                    recommendation[1],
                    f"reject-after-auth-{context.suffix}",
                    "Timing changed after authorization",
                ),
            )
            with PostgresProspectingUnitOfWork(context.connection_factory) as work:
                PostgresDigestSubscriptionAccess(work.connection).unsubscribe(
                    context.owner_user_id,
                    context.business_id,
                    context.current_time[0] + timedelta(seconds=2),
                )
                work.commit()
            context.current_time[0] = actual_acceptance + timedelta(seconds=1)
            return actual_acceptance

    service = _make_service(context, OptOutAfterAuthorizationSender())
    result = service.run()
    assert result["sent"] == 1
    assert len(sent_messages) == 1
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT enabled FROM operational.weekly_digest_subscriptions "
                "WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            is False
        )
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == "sent"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND kind='cooldown'",
                (context.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert connection.execute(
            "SELECT status,first_presented_at FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone() == ("rejected", actual_acceptance)
        assert connection.execute(
            "SELECT kind,effective_at FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s ORDER BY kind",
            (context.business_id, context.company_id),
        ).fetchall() == [
            ("cooldown", actual_acceptance),
            ("rejection", rejection_at),
        ]


def test_recipient_change_before_authorization_suppresses_old_frozen_recipient(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)
    replacement_email = f"replacement-{context.suffix}@example.test"

    class Sender:
        def send(self, message):
            raise AssertionError("Stale recipient content must not reach SMTP")

    service = _make_service(context, Sender())
    base_authorize = service._authorize

    def authorize_after_recipient_change(*args):
        context.current_time[0] += timedelta(seconds=2)
        with psycopg.connect(context.database_url) as connection:
            connection.execute(
                "UPDATE operational.account_recovery_identity "
                "SET verified_email=%s,verified_at=%s WHERE account_id=%s",
                (replacement_email, context.current_time[0], context.account_id),
            )
        return base_authorize(*args)

    service._authorize = authorize_after_recipient_change
    assert service.run()["skipped"] == 1
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT verified_email FROM operational.account_recovery_identity "
                "WHERE account_id=%s",
                (context.account_id,),
            ).fetchone()[0]
            == replacement_email
        )
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == "suppressed"
        )
        assert (
            connection.execute(
                "SELECT DISTINCT c.recipient FROM operational.weekly_digest_contents c "
                "WHERE c.business_id=%s",
                (context.business_id,),
            ).fetchall()
            == []
        )
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE business_id=%s",
                (context.business_id,),
            ).fetchall()
            == []
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND kind='cooldown'",
                (context.business_id,),
            ).fetchone()[0]
            == 0
        )


def test_proven_pretransport_failure_abandons_claim_without_exposure(
    weekly_service_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)

    class PreTransportFailure:
        def send(self, message):
            raise MailPreTransportError("Message rejected before SMTP transport")

    service = _make_service(context, PreTransportFailure())
    result = service.run()
    assert result["failed"] == 1
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == "failed"
        )
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == "abandoned"
        )
        assert (
            connection.execute(
                "SELECT first_presented_at FROM operational.recommendations "
                "WHERE business_id=%s AND company_id=%s",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            is None
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "acknowledgement",
    [None, datetime(2026, 11, 15, 12)],
    ids=["missing", "naive"],
)
def test_malformed_smtp_acceptance_is_unknown_without_invented_presentation_time(
    weekly_service_database_url, monkeypatch, acknowledgement
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    _subscribe(context)

    class MalformedAcknowledgementSender:
        calls = 0

        def send(self, message):
            self.calls += 1
            return acknowledgement

    sender = MalformedAcknowledgementSender()
    result = _make_service(context, sender).run()
    assert result["unknown"] == 1
    assert sender.calls == 1
    with psycopg.connect(context.database_url) as connection:
        delivery = connection.execute(
            "SELECT state,accepted_at FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s",
            (context.business_id,),
        ).fetchone()
        assert delivery == ("unknown", None)
        cycle = connection.execute(
            "SELECT id,status,presented_at FROM operational.offer_cycles "
            "WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
        assert cycle[1:] == ("unknown", None)
        assert connection.execute(
            "SELECT presented_at FROM operational.offer_cycle_events "
            "WHERE offer_cycle_id=%s AND event_kind='sending_unknown'",
            (cycle[0],),
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT first_presented_at FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone() == (None,)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("outcome", ["sent", "failed"])
def test_stopped_sender_reconciliation_preserves_frozen_delivery_and_cadence(
    weekly_service_database_url, monkeypatch, outcome
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (context.company_id,)
        )
    _subscribe(context)
    actual_accepted = context.current_time[0] + timedelta(seconds=2)

    class Sender:
        calls = 0

        def send(self, message):
            self.calls += 1
            return actual_accepted

    sender = Sender()
    service = _make_service(context, sender)
    authorized = []
    original_authorize = service._authorize
    original_settle = service._settle_transport

    def remember_authorization(*args):
        result = original_authorize(*args)
        authorized.append(result)
        return result

    monkeypatch.setattr(service, "_authorize", remember_authorization)

    def settlement_failed(*args, **kwargs):
        raise RuntimeError("Settlement database unavailable after SMTP")

    monkeypatch.setattr(service, "_settle_transport", settlement_failed)
    assert service.run()["failed"] == 1
    with psycopg.connect(context.database_url) as connection:
        delivery_id, version, content_id, started_at = connection.execute(
            "SELECT id,version,current_content_id,sending_started_at FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s AND state='sending'",
            (context.business_id,),
        ).fetchone()
        frozen_content = connection.execute(
            "SELECT * FROM operational.weekly_digest_contents WHERE id=%s",
            (content_id,),
        ).fetchone()
        frozen_members = connection.execute(
            "SELECT * FROM operational.weekly_digest_members WHERE content_id=%s",
            (content_id,),
        ).fetchall()
        cycle_ids = tuple(
            row[0]
            for row in connection.execute(
                "SELECT offer_cycle_id FROM operational.weekly_digest_members WHERE content_id=%s ORDER BY position",
                (content_id,),
            ).fetchall()
        )
        authorization_events = connection.execute(
            "SELECT * FROM operational.offer_cycle_events WHERE offer_cycle_id=ANY(%s) AND event_kind='sending_authorized'",
            (list(cycle_ids),),
        ).fetchall()
        connection.execute(
            "UPDATE operational.business_recommendation_preferences SET repeat_interval_days=60,updated_at=updated_at+interval '1 second' WHERE business_id=%s",
            (context.business_id,),
        )
        block_id = uuid4()
        connection.execute(
            "INSERT INTO operational.suppression_blocks (id,business_id,company_id,kind,created_at,effective_at,expires_at,created_by_user_id,reason) "
            "VALUES (%s,%s,%s,'pause',%s,%s,%s,%s,'Independent pause')",
            (
                block_id,
                context.business_id,
                context.company_id,
                context.current_time[0],
                context.current_time[0],
                context.current_time[0] + timedelta(days=90),
                context.owner_user_id,
            ),
        )
        independent_block = connection.execute(
            "SELECT * FROM operational.suppression_blocks WHERE id=%s", (block_id,)
        ).fetchone()

    context.current_time[0] += timedelta(days=35)
    # Age alone cannot release Sending protection or cause a second handoff.
    assert service.run()["sent"] == 0
    assert sender.calls == 1
    recover = RecoverWeeklyDigestService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        delivery_repository_factory=lambda work: PostgresWeeklyDigestDeliveryRepository(
            work.connection
        ),
        content_repository_factory=lambda work: PostgresWeeklyDigestContentRepository(
            work.connection
        ),
        clock=lambda: context.current_time[0],
    )
    request = ReconcileStoppedWeeklyDigestRequest(
        delivery_id,
        version,
        content_id,
        started_at,
        cycle_ids,
        True,
        "Original sender exited; host process absence verified",
    )
    for changes in (
        {"expected_version": version + 1},
        {"expected_content_id": uuid4()},
        {"expected_offer_cycle_ids": (uuid4(),)},
        {"expected_sending_started_at": started_at + timedelta(seconds=1)},
    ):
        with pytest.raises(ConflictError):
            recover.reconcile_stopped_sender(
                context.principal, replace(request, **changes)
            )
    reconciled = recover.reconcile_stopped_sender(context.principal, request)
    assert reconciled.state == "unknown"
    with pytest.raises(ConflictError):
        original_settle(*authorized[0], "sent", accepted_at=actual_accepted)
    assert recover.reconcile_stopped_sender(context.principal, request) == reconciled
    with pytest.raises(ConflictError):
        recover.reconcile_stopped_sender(
            context.principal, replace(request, reason="Different evidence")
        )

    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT status,presented_at FROM operational.offer_cycles WHERE id=ANY(%s)",
            (list(cycle_ids),),
        ).fetchall() == [("unknown", None)]
        assert connection.execute(
            "SELECT actor_user_id,reason FROM operational.offer_cycle_events WHERE offer_cycle_id=ANY(%s) AND event_kind='sending_unknown'",
            (list(cycle_ids),),
        ).fetchall() == [(context.owner_user_id, request.reason)]
        assert connection.execute(
            "SELECT actor_user_id,reason FROM operational.weekly_digest_delivery_events WHERE delivery_id=%s AND event_kind='unknown'",
            (delivery_id,),
        ).fetchall() == [(context.owner_user_id, request.reason)]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks WHERE business_id=%s AND kind='cooldown'",
                (context.business_id,),
            ).fetchone()[0]
            == 0
        )

    result = recover.execute(
        context.principal,
        RecoverWeeklyDigestRequest(
            delivery_id,
            "Provider audit confirms actual outcome",
            outcome,
            actual_accepted if outcome == "sent" else None,
        ),
    )
    assert result.state == outcome
    assert recover.reconcile_stopped_sender(context.principal, request) == result
    assert sender.calls == 1
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT * FROM operational.weekly_digest_contents WHERE id=%s",
                (content_id,),
            ).fetchone()
            == frozen_content
        )
        assert (
            connection.execute(
                "SELECT * FROM operational.weekly_digest_members WHERE content_id=%s",
                (content_id,),
            ).fetchall()
            == frozen_members
        )
        assert (
            connection.execute(
                "SELECT * FROM operational.offer_cycle_events WHERE offer_cycle_id=ANY(%s) AND event_kind='sending_authorized'",
                (list(cycle_ids),),
            ).fetchall()
            == authorization_events
        )
        assert (
            connection.execute(
                "SELECT * FROM operational.suppression_blocks WHERE id=%s", (block_id,)
            ).fetchone()
            == independent_block
        )
        assert connection.execute(
            "SELECT status,presented_at FROM operational.offer_cycles WHERE id=ANY(%s)",
            (list(cycle_ids),),
        ).fetchall() == [
            (
                "confirmed" if outcome == "sent" else "abandoned",
                actual_accepted if outcome == "sent" else None,
            )
        ]
        cooldowns = connection.execute(
            "SELECT effective_at,expires_at FROM operational.suppression_blocks WHERE business_id=%s AND kind='cooldown'",
            (context.business_id,),
        ).fetchall()
        assert cooldowns == (
            [(actual_accepted, actual_accepted + timedelta(days=30))]
            if outcome == "sent"
            else []
        )


@pytest.mark.parametrize("error_type", [RuntimeError, TypeError])
def test_unexpected_candidate_failure_is_persisted_as_failed_without_smtp(
    weekly_service_database_url, monkeypatch, error_type
):
    context = seed_retained_brightroom_context(weekly_service_database_url, monkeypatch)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (context.company_id,)
        )
    _subscribe(context)

    class Sender:
        def send(self, message):
            raise AssertionError("Unexpected preparation failure must not contact SMTP")

    service = _make_service(context, Sender())

    def selection_failure(*args):
        raise error_type("Unexpected current selection failure")

    monkeypatch.setattr(
        "huginn.management.application.services.weekly_digest.load_current_offer_selection",
        selection_failure,
    )
    result = service.run()
    assert result["failed"] == 1
    assert result["skipped"] == result["sent"] == 0
    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT state FROM operational.weekly_digest_deliveries WHERE business_id=%s",
            (context.business_id,),
        ).fetchall() == [("failed",)]
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE business_id=%s",
                (context.business_id,),
            ).fetchall()
            == []
        )
        for table in ("weekly_digest_contents", "offer_cycle_events"):
            assert connection.execute(
                f"SELECT count(*) FROM operational.{table} WHERE business_id=%s",
                (context.business_id,),
            ).fetchone() == (0,)
        assert connection.execute(
            "SELECT first_presented_at FROM operational.recommendations WHERE business_id=%s",
            (context.business_id,),
        ).fetchall() == [(None,)]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks WHERE business_id=%s",
                (context.business_id,),
            ).fetchone()[0]
            == 0
        )
