"""Rollback disables new discovery work without erasing owned history."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from huginn.management.app import create_app
from huginn.management.application.requests.confirm_recommendation_offer_request import (
    ConfirmRecommendationOfferRequest,
)
from huginn.management.application.requests.prepare_recommendation_offer_request import (
    PrepareRecommendationOfferRequest,
)
from huginn.management.application.services.recommendation_offer_service import (
    RecommendationOfferService,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
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
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.security.tokens import digest_token
from huginn.management.weekly_digest_bootstrap import create_weekly_digest_service
from tests.management.persistence.retained_prospecting_fixtures import (
    generate_retained_brightroom_selection,
    seed_retained_brightroom_context,
)
from tests.postgres_harness import SCHEMA_FILES, provisioned_postgres

_CLEANUP = Path("db/schema/operational-obsolete-prospecting-cleanup.sql")
_CSRF = "rollback-owner-csrf"
_HISTORY_TABLES = (
    "recommendations",
    "assessment_revisions",
    "offer_cycles",
    "offer_cycle_events",
    "prospects",
    "prospect_origins",
    "prospect_activities",
    "suppression_blocks",
    "command_receipts",
    "recommendation_assessment_feedback",
    "weekly_digest_subscriptions",
    "weekly_digest_deliveries",
    "weekly_digest_contents",
    "weekly_digest_members",
    "weekly_digest_delivery_events",
)


@pytest.fixture
def rollback_database_url():
    with provisioned_postgres(
        "huginn_prospecting_rollback_test", apply_schema=False
    ) as url:
        with psycopg.connect(url, autocommit=True) as connection:
            for filename in SCHEMA_FILES:
                if filename == "operational-weekly-digest-content.sql":
                    continue
                connection.execute((Path("db/schema") / filename).read_text())
        yield url


def _seed_one_legacy_record(connection, context) -> tuple:
    match_id = connection.execute(
        "INSERT INTO operational.match(user_id,company_id,notes) "
        "VALUES (%s,%s,'rollback rehearsal legacy row') RETURNING id",
        (context.owner_user_id, context.company_id),
    ).fetchone()[0]
    batch_id = uuid4()
    connection.execute(
        "INSERT INTO operational.recommendation_batches "
        "(id,user_id,strategy_id,created_at,snapshot) VALUES (%s,%s,%s,%s,%s)",
        (
            batch_id,
            context.owner_user_id,
            context.strategy_id,
            context.current_time[0],
            Jsonb({"items": [{"id": "legacy"}]}),
        ),
    )
    return match_id, batch_id


def _history_snapshot(connection, business_id):
    return {
        table: connection.execute(
            f"SELECT coalesce(jsonb_agg(to_jsonb(row) ORDER BY to_jsonb(row)::text),"
            f"'[]'::jsonb) FROM operational.{table} row WHERE business_id=%s",
            (business_id,),
        ).fetchone()[0]
        for table in _HISTORY_TABLES
    }


def _identity_configuration_snapshot(connection, context):
    return (
        connection.execute(
            "SELECT id,username,status FROM operational.accounts WHERE id=%s",
            (context.account_id,),
        ).fetchone(),
        connection.execute(
            "SELECT id,first_name,last_name,email,phone_number,country_of_residence "
            "FROM operational.users WHERE id=%s",
            (context.owner_user_id,),
        ).fetchone(),
        connection.execute(
            "SELECT to_jsonb(profile) FROM operational.professional_profiles profile "
            "WHERE user_id=%s",
            (context.owner_user_id,),
        ).fetchone()[0],
        connection.execute(
            "SELECT business_id,repeat_interval_days,updated_at "
            "FROM operational.business_recommendation_preferences WHERE business_id=%s",
            (context.business_id,),
        ).fetchone(),
        connection.execute(
            "SELECT s.id,s.service_offering_id,s.ideal_client_profile_id,o.name,o.description,"
            "i.name,i.geographies FROM operational.client_discovery_strategies s "
            "JOIN operational.service_offerings o ON o.id=s.service_offering_id "
            "JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id "
            "WHERE s.business_id=%s ORDER BY s.id",
            (context.business_id,),
        ).fetchall(),
    )


def _subscribe(context) -> None:
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "INSERT INTO operational.account_recovery_identity "
            "(account_id,verification_required,verified_email,verified_at) "
            "VALUES (%s,true,%s,%s)",
            (
                context.account_id,
                f"rollback-{context.suffix}@example.test",
                context.current_time[0],
            ),
        )
    with PostgresProspectingUnitOfWork(context.connection_factory) as work:
        PostgresDigestSubscriptionAccess(work.connection).subscribe(
            context.owner_user_id, context.business_id, context.current_time[0]
        )
        work.commit()


def _seed_actual_offer(context, selected):
    prepare = RecommendationOfferService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: context.current_time[0],
    )
    prepared = prepare.prepare(
        context.principal,
        PrepareRecommendationOfferRequest(
            selected.recommendation_id,
            selected.revision_id,
            f"rollback-seed-{context.suffix}",
        ),
    )
    confirm = RecommendationOfferService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: context.current_time[0],
    )
    return confirm.confirm(
        context.principal,
        ConfirmRecommendationOfferRequest(
            prepared.offer_cycle_id, prepared.claim_token
        ),
    )


def _seed_unknown_weekly_delivery(context):
    class UnknownSender:
        def send(self, _message):
            raise OSError("Rollback rehearsal ambiguous SMTP outcome")

    factory = context.connection_factory

    def make_work():
        return PostgresProspectingUnitOfWork(factory)

    service = WeeklyDigestService(
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
        generation=context.generation_service,
        renderer=_renderer(context),
        sender=UnknownSender(),
        sender_address="weekly@huginn.example",
        clock=lambda: context.current_time[0],
    )
    result = service.run()
    if result["unknown"] != 1 or result["sent"] != 0:
        raise AssertionError(f"Expected an Unknown weekly delivery, got {result}")
    with psycopg.connect(context.database_url) as connection:
        return connection.execute(
            "SELECT id,state FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s",
            (context.business_id,),
        ).fetchone()


def _renderer(context):
    from huginn.management.delivery.templates.weekly_digest import (
        PlainTextWeeklyDigestRenderer,
    )

    return PlainTextWeeklyDigestRenderer(
        "https://huginn.example", "rollback-signing-key", "huginn.example"
    )


def test_rollback_blocks_only_new_discovery_and_preserves_activity_and_history(
    rollback_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(rollback_database_url, monkeypatch)
    with psycopg.connect(context.database_url, autocommit=True) as connection:
        legacy_match_id, legacy_batch_id = _seed_one_legacy_record(connection, context)
        connection.execute(_CLEANUP.read_text(encoding="utf-8"))
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.match WHERE id=%s", (legacy_match_id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendation_batches WHERE id=%s",
                (legacy_batch_id,),
            ).fetchone()[0]
            == 0
        )
        connection.execute(
            Path("db/schema/operational-weekly-digest-content.sql").read_text(
                encoding="utf-8"
            )
        )

    selected = generate_retained_brightroom_selection(context)
    confirmed = _seed_actual_offer(context, selected)
    assert confirmed.offer_cycle_id
    _subscribe(context)
    context.current_time[0] = confirmed.presented_at + timedelta(days=35)
    unknown_delivery = _seed_unknown_weekly_delivery(context)
    assert unknown_delivery[1] == "unknown"

    app_config = ManagementConfig(
        context.database_url,
        environment="test",
        discovery_new_work_enabled=False,
    )
    app = create_app(app_config, clock=lambda: context.current_time[0])
    now = context.current_time[0]
    session = Session(
        uuid4(),
        context.account_id,
        "rollback-session-token",
        digest_token(_CSRF),
        now,
        now + timedelta(hours=1),
        None,
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        context.principal, session, "opaque-test-session"
    )

    # The scheduled entry point rejects the disabled state before it can even
    # construct a database connection factory.
    import huginn.management.weekly_digest_bootstrap as weekly_bootstrap

    def no_database_factory(*_args, **_kwargs):
        raise AssertionError("Disabled weekly composition must not touch database IO")

    monkeypatch.setattr(
        weekly_bootstrap, "ManagementConnectionFactory", no_database_factory
    )
    with pytest.raises(ValueError, match="disabled"):
        create_weekly_digest_service(app_config)

    with psycopg.connect(context.database_url) as connection:
        before_blocked_work = _history_snapshot(connection, context.business_id)
        identity_configuration_before = _identity_configuration_snapshot(
            connection, context
        )
        current_rec = connection.execute(
            "SELECT id,current_revision_id,version FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s",
            (context.business_id, context.company_id),
        ).fetchone()
        unknown_cycle = connection.execute(
            "SELECT id,claim_token FROM operational.offer_cycles "
            "WHERE business_id=%s AND status='unknown'",
            (context.business_id,),
        ).fetchone()
        preferences = connection.execute(
            "SELECT repeat_interval_days,updated_at "
            "FROM operational.business_recommendation_preferences WHERE business_id=%s",
            (context.business_id,),
        ).fetchone()
    assert current_rec is not None and unknown_cycle is not None

    with TestClient(app) as client:
        headers = {"X-CSRF-Token": _CSRF}
        generation = client.post(
            "/api/v1/recommendations",
            json={"strategy_id": str(context.strategy_id), "limit": 10},
            headers=headers,
        )
        preparation = client.post(
            f"/api/v1/recommendations/{current_rec[0]}/offer-preparations",
            json={
                "assessment_revision_id": str(current_rec[1]),
                "request_key": f"rollback-disabled-{context.suffix}",
            },
            headers=headers,
        )
        confirmation = client.post(
            f"/api/v1/recommendations/offer-preparations/{unknown_cycle[0]}/confirm",
            json={"claim_token": unknown_cycle[1]},
            headers=headers,
        )
        for response in (generation, preparation, confirmation):
            assert response.status_code == 503, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["vary"] == "Cookie"

        current_read = client.get(f"/api/v1/recommendations/{current_rec[0]}")
        exact_read = client.get(
            f"/api/v1/recommendations/{current_rec[0]}",
            params={"assessment_revision_id": str(current_rec[1])},
        )
        assert current_read.status_code == exact_read.status_code == 200
        assert exact_read.json()["assessment"]["id"] == str(current_rec[1])
        with psycopg.connect(context.database_url) as connection:
            assert _history_snapshot(connection, context.business_id) == (
                before_blocked_work
            )

        # Existing discovery management and pursuit remain available during
        # rollback. A Later pause can be cancelled without clearing Unknown.
        later = client.post(
            f"/api/v1/recommendations/{current_rec[0]}/later",
            json={
                "assessment_revision_id": str(current_rec[1]),
                "expected_recommendation_version": current_rec[2],
                "request_key": f"rollback-later-{context.suffix}",
                "pause_choice": "x1",
                "expected_repeat_interval_days": preferences[0],
                "expected_preference_updated_at": preferences[1].isoformat(),
                "expected_pause_id": None,
                "expected_pause_version": None,
            },
            headers=headers,
        )
        assert later.status_code == 200, later.text
        pause_id = later.json()["suppression_block_id"]
        cancel = client.post(
            f"/api/v1/suppressions/{pause_id}/cancel-pause",
            json={
                "expected_version": 1,
                "request_key": f"rollback-cancel-pause-{context.suffix}",
            },
            headers=headers,
        )
        assert cancel.status_code == 200, cancel.text

        rejected = client.post(
            f"/api/v1/recommendations/{current_rec[0]}/not-relevant",
            json={
                "assessment_revision_id": str(current_rec[1]),
                "expected_recommendation_version": current_rec[2],
                "request_key": f"rollback-reject-{context.suffix}",
                "reason": "Reviewed during rollback",
            },
            headers=headers,
        )
        assert rejected.status_code == 200, rejected.text
        rejection_id = rejected.json()["suppression_block_id"]
        reverse = client.post(
            f"/api/v1/suppressions/{rejection_id}/reverse-rejection",
            json={
                "expected_version": 1,
                "request_key": f"rollback-reverse-rejection-{context.suffix}",
            },
            headers=headers,
        )
        assert reverse.status_code == 200, reverse.text

        saved = client.post(
            f"/api/v1/recommendations/{current_rec[0]}/save",
            json={
                "assessment_revision_id": str(current_rec[1]),
                "request_key": f"rollback-save-{context.suffix}",
            },
            headers=headers,
        )
        assert saved.status_code == 200, saved.text
        prospect_id = saved.json()["prospect_id"]
        stage = client.post(
            f"/api/v1/prospects/{prospect_id}/stage",
            json={
                "expected_version": 1,
                "request_key": f"rollback-stage-{context.suffix}",
                "occurred_at": context.current_time[0].isoformat(),
                "target_stage": "contacted",
                "reason": "Rollback rehearsal retained activity",
            },
            headers=headers,
        )
        assert stage.status_code == 200, stage.text
        notes = client.post(
            f"/api/v1/prospects/{prospect_id}/notes",
            json={
                "expected_version": 2,
                "request_key": f"rollback-notes-{context.suffix}",
                "occurred_at": context.current_time[0].isoformat(),
                "replacement_notes": "Keep this owner-authored note after rollback.",
            },
            headers=headers,
        )
        assert notes.status_code == 200, notes.text

        with psycopg.connect(context.database_url) as connection:
            unknown_cycle = connection.execute(
                "SELECT id,sending_started_at,status FROM operational.offer_cycles "
                "WHERE business_id=%s AND status='unknown'",
                (context.business_id,),
            ).fetchone()
            actual_accepted_at = unknown_cycle[1] + timedelta(seconds=5)
        context.current_time[0] = actual_accepted_at + timedelta(seconds=5)
        recovered = client.post(
            f"/api/v1/weekly-digests/{unknown_delivery[0]}/recovery",
            json={
                "outcome": "sent",
                "reason": "Verified accepted after rollback",
                "accepted_at": actual_accepted_at.isoformat(),
            },
            headers=headers,
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["state"] == "sent"
        assert recovered.headers["cache-control"] == "no-store"

    with psycopg.connect(context.database_url, autocommit=True) as connection:
        before_cleanup_replay = _history_snapshot(connection, context.business_id)
        with pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState,
            match="new workflow history",
        ):
            connection.execute(_CLEANUP.read_text(encoding="utf-8"))
        connection.rollback()
        after_cleanup_replay = _history_snapshot(connection, context.business_id)
        assert after_cleanup_replay == before_cleanup_replay
        assert connection.execute(
            "SELECT status,first_presented_at FROM operational.recommendations "
            "WHERE id=%s",
            (current_rec[0],),
        ).fetchone() == ("rejected", confirmed.presented_at)
        assert connection.execute(
            "SELECT stage,notes,version FROM operational.prospects WHERE id=%s",
            (prospect_id,),
        ).fetchone() == (
            "contacted",
            "Keep this owner-authored note after rollback.",
            3,
        )
        assert connection.execute(
            "SELECT recommendation_id,assessment_revision_id FROM operational.prospect_origins "
            "WHERE prospect_id=%s",
            (prospect_id,),
        ).fetchone() == (current_rec[0], current_rec[1])
        assert connection.execute(
            "SELECT status,presented_at FROM operational.offer_cycles WHERE id=%s",
            (unknown_cycle[0],),
        ).fetchone() == ("confirmed", actual_accepted_at)
        suppression_rows = connection.execute(
            "SELECT id,kind,cleared_at FROM operational.suppression_blocks "
            "WHERE id IN (%s,%s) ORDER BY kind",
            (pause_id, rejection_id),
        ).fetchall()
        assert {str(row[0]) for row in suppression_rows} == {pause_id, rejection_id}
        assert {row[1] for row in suppression_rows} == {"pause", "rejection"}
        assert all(row[2] is not None for row in suppression_rows)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_delivery_events "
                "WHERE delivery_id=%s AND event_kind='unknown_resolved'",
                (unknown_delivery[0],),
            ).fetchone()[0]
            == 1
        )
        expected_identity_configuration = (
            context.account_before,
            context.user_before,
            context.personal_profile_before,
            context.preferences_before,
            context.configuration_before,
        )
        assert identity_configuration_before == expected_identity_configuration
        assert (
            _identity_configuration_snapshot(connection, context)
            == expected_identity_configuration
        )
