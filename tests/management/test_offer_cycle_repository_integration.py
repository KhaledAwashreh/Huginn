from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.entities.offer_cycle import OfferCycle
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.accepted_offer_cadence import (
    AcceptedOfferCadence,
)
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from huginn.management.persistence.repositories.offer_cycle import (
    PostgresOfferCycleRepository,
)
from huginn.management.persistence.repositories.recommendation import (
    PostgresRecommendationRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_assessment_revision,
    valid_recommendation,
)


def _cadence(at: datetime, days: int = 30) -> AcceptedOfferCadence:
    return AcceptedOfferCadence(days, at, at)


def test_unknown_recovery_preserves_handoff_and_appends_atomic_audit_history(
    management_database_url,
):
    acquired_at = datetime(2026, 11, 14, 12, tzinfo=UTC)
    send_started_at = acquired_at + timedelta(minutes=1)
    timeout_observed_at = acquired_at + timedelta(minutes=5)
    accepted_at = acquired_at + timedelta(minutes=10)
    recovered_at = acquired_at + timedelta(minutes=35)
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendations = PostgresRecommendationRepository(session)
        revisions = PostgresAssessmentRevisionRepository(session)
        recommendation = recommendations.create_open(
            valid_recommendation(identity, at=acquired_at)
        )
        revision = revisions.append(
            valid_assessment_revision(identity, recommendation, at=acquired_at)
        )
        recommendation_id, revision_id = recommendation.id, revision.id
        repository = PostgresOfferCycleRepository(session)
        cycle = OfferCycle(
            id=uuid4(),
            business_id=identity.business_id,
            company_id=identity.company_id,
            recommendation_id=recommendation_id,
            selected_revision_id=revision_id,
            idempotency_key="offer-cycle-test-key",
            payload_fingerprint="a" * 64,
            status=OfferCycleStatus("preparing"),
            created_at=acquired_at,
            updated_at=acquired_at,
            claim_token="claim-token-1",
            lease_expires_at=acquired_at + timedelta(minutes=15),
        )

        acquired = repository.acquire_preparing(
            cycle,
            now=acquired_at,
            lease_expires_at=cycle.lease_expires_at,
            claim_token=cycle.claim_token,
        )
        assert acquired == cycle
        assert (
            repository.get_by_request_key(identity.business_id, cycle.idempotency_key)
            == cycle
        )
        assert repository.get_by_request_key(uuid4(), cycle.idempotency_key) is None
        assert (
            repository.get_pending(identity.business_id, identity.company_id) == cycle
        )
        other_business_id = uuid4()
        assert repository.get_pending(other_business_id, identity.company_id) is None
        with pytest.raises(ConflictError):
            repository.mark_sending(
                other_business_id,
                identity.company_id,
                cycle.id,
                cycle.claim_token,
                send_started_at,
                _cadence(send_started_at),
            )
        with pytest.raises(ConflictError):
            repository.mark_sending(
                identity.business_id,
                identity.company_id,
                cycle.id,
                "wrong-claim-token",
                send_started_at,
                _cadence(send_started_at),
            )

        sending = repository.mark_sending(
            identity.business_id,
            identity.company_id,
            cycle.id,
            cycle.claim_token,
            send_started_at,
            _cadence(send_started_at),
        )
        assert sending.status.value == "sending"
        unknown = repository.settle_sending(
            identity.business_id,
            identity.company_id,
            cycle.id,
            cycle.claim_token,
            "unknown",
            timeout_observed_at,
        )
        assert unknown.status.value == "unknown"
        assert (
            repository.release_expired_preparing(
                identity.business_id,
                identity.company_id,
                cycle.id,
                recovered_at,
            )
            is False
        )

        confirmed = repository.resolve_unknown(
            identity.business_id,
            identity.company_id,
            cycle.id,
            identity.owner_user_id,
            "Provider confirmed delivery after timeout",
            "confirmed",
            accepted_at,
            recovered_at,
        )
        assert confirmed.status.value == "confirmed"
        assert confirmed.presented_at == accepted_at
        assert confirmed.settled_at == recovered_at
        assert repository.get_pending(identity.business_id, identity.company_id) is None

        persisted = connection.execute(
            "SELECT status,sending_started_at,settled_at,presented_at "
            "FROM operational.offer_cycles WHERE id=%s",
            (cycle.id,),
        ).fetchone()
        events = connection.execute(
            "SELECT event_kind,outcome,presented_at,resolved_at,recorded_at,"
            "actor_user_id,reason FROM operational.offer_cycle_events "
            "WHERE offer_cycle_id=%s ORDER BY recorded_at,id",
            (cycle.id,),
        ).fetchall()
        assert persisted == ("confirmed", send_started_at, recovered_at, accepted_at)
        assert [event[0] for event in events] == [
            "preparing_acquired",
            "sending_authorized",
            "sending_unknown",
            "unknown_resolved",
        ]
        assert events[2][4] == timeout_observed_at
        assert events[3] == (
            "unknown_resolved",
            "confirmed",
            accepted_at,
            recovered_at,
            recovered_at,
            identity.owner_user_id,
            "Provider confirmed delivery after timeout",
        )


def test_app_and_smtp_authorization_persist_accepted_cadence_immutably(
    management_database_url,
):
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendation = PostgresRecommendationRepository(session).create_open(
            valid_recommendation(identity, at=now)
        )
        revision = PostgresAssessmentRevisionRepository(session).append(
            valid_assessment_revision(identity, recommendation, at=now)
        )
        repository = PostgresOfferCycleRepository(session)

        def acquire(key, started_at):
            cycle = OfferCycle(
                id=uuid4(),
                business_id=identity.business_id,
                company_id=identity.company_id,
                recommendation_id=recommendation.id,
                selected_revision_id=revision.id,
                idempotency_key=key,
                payload_fingerprint="d" * 64,
                status=OfferCycleStatus("preparing"),
                created_at=started_at,
                updated_at=started_at,
                claim_token=f"claim-{key}",
                lease_expires_at=started_at + timedelta(minutes=5),
            )
            return repository.acquire_preparing(
                cycle,
                now=started_at,
                lease_expires_at=cycle.lease_expires_at,
                claim_token=cycle.claim_token,
            )

        app_cycle = acquire("cadence-app", now)
        app_confirmed_at = now + timedelta(minutes=1)
        app_cadence = _cadence(app_confirmed_at, 30)
        repository.confirm_preparing(
            identity.business_id,
            identity.company_id,
            app_cycle.id,
            app_cycle.claim_token,
            app_confirmed_at,
            app_cadence,
            identity.owner_user_id,
        )
        connection.execute(
            "UPDATE operational.business_recommendation_preferences "
            "SET repeat_interval_days=45 WHERE business_id=%s",
            (identity.business_id,),
        )
        replayed = repository.confirm_preparing(
            identity.business_id,
            identity.company_id,
            app_cycle.id,
            app_cycle.claim_token,
            now + timedelta(minutes=2),
            _cadence(now + timedelta(minutes=2), 45),
            identity.owner_user_id,
        )
        assert replayed.presented_at == app_confirmed_at
        assert replayed.claim_token is None
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.offer_cycles SET claim_token=%s WHERE id=%s",
                (app_cycle.claim_token, app_cycle.id),
            )
        assert (
            repository.accepted_cadence(
                identity.business_id, identity.company_id, app_cycle.id
            )
            == app_cadence
        )

        smtp_cycle = acquire("cadence-smtp", now + timedelta(minutes=3))
        authorized_at = now + timedelta(minutes=4)
        smtp_cadence = _cadence(authorized_at, 45)
        repository.mark_sending(
            identity.business_id,
            identity.company_id,
            smtp_cycle.id,
            smtp_cycle.claim_token,
            authorized_at,
            smtp_cadence,
        )
        connection.execute(
            "UPDATE operational.business_recommendation_preferences "
            "SET repeat_interval_days=60 WHERE business_id=%s",
            (identity.business_id,),
        )
        assert (
            repository.accepted_cadence(
                identity.business_id, identity.company_id, smtp_cycle.id
            )
            == smtp_cadence
        )
        events = connection.execute(
            "SELECT event_kind,actor_user_id,recorded_at,payload "
            "FROM operational.offer_cycle_events WHERE offer_cycle_id=%s "
            "AND event_kind='preparing_confirmed'",
            (app_cycle.id,),
        ).fetchone()
        assert events[:3] == (
            "preparing_confirmed",
            identity.owner_user_id,
            app_confirmed_at,
        )
        assert events[3]["repeat_interval_days"] == 30
        assert events[3]["preference_updated_at"] == app_confirmed_at.isoformat()
        assert events[3]["accepted_at"] == app_confirmed_at.isoformat()
        assert events[3]["claim_token_fingerprint"]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycle_events "
                "WHERE offer_cycle_id=%s AND event_kind='preparing_confirmed'",
                (app_cycle.id,),
            ).fetchone()[0]
            == 1
        )


def test_preparing_expiry_sending_failure_and_claim_conflicts(management_database_url):
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendation = PostgresRecommendationRepository(session).create_open(
            valid_recommendation(identity, at=now)
        )
        revision = PostgresAssessmentRevisionRepository(session).append(
            valid_assessment_revision(identity, recommendation, at=now)
        )
        repository = PostgresOfferCycleRepository(session)

        def draft(key: str, created_at: datetime) -> OfferCycle:
            return OfferCycle(
                id=uuid4(),
                business_id=identity.business_id,
                company_id=identity.company_id,
                recommendation_id=recommendation.id,
                selected_revision_id=revision.id,
                idempotency_key=key,
                payload_fingerprint="b" * 64,
                status=OfferCycleStatus("preparing"),
                created_at=created_at,
                updated_at=created_at,
                claim_token=f"claim-{key}",
                lease_expires_at=created_at + timedelta(minutes=5),
            )

        expired = draft("expired-preparing", now)
        repository.acquire_preparing(
            expired,
            now=now,
            lease_expires_at=expired.lease_expires_at,
            claim_token=expired.claim_token,
        )
        with pytest.raises(ConflictError):
            repository.confirm_preparing(
                identity.business_id,
                identity.company_id,
                expired.id,
                expired.claim_token,
                expired.lease_expires_at,
                _cadence(expired.lease_expires_at),
                identity.owner_user_id,
            )
        assert repository.release_expired_preparing(
            identity.business_id,
            identity.company_id,
            expired.id,
            expired.lease_expires_at,
        )
        assert not repository.release_expired_preparing(
            identity.business_id,
            identity.company_id,
            expired.id,
            expired.lease_expires_at + timedelta(seconds=1),
        )
        assert repository.get_pending(identity.business_id, identity.company_id) is None

        explicit = draft(
            "explicit-abandon", expired.lease_expires_at + timedelta(seconds=1)
        )
        repository.acquire_preparing(
            explicit,
            now=explicit.created_at,
            lease_expires_at=explicit.lease_expires_at,
            claim_token=explicit.claim_token,
        )
        abandoned_at = explicit.created_at + timedelta(minutes=1)
        explicitly_abandoned = repository.abandon_preparing(
            identity.business_id,
            identity.company_id,
            explicit.id,
            explicit.claim_token,
            identity.owner_user_id,
            "User canceled before sending",
            abandoned_at,
        )
        assert (explicitly_abandoned.status.value, explicitly_abandoned.settled_at) == (
            "abandoned",
            abandoned_at,
        )

        in_app = draft("in-app-confirm", abandoned_at)
        repository.acquire_preparing(
            in_app,
            now=in_app.created_at,
            lease_expires_at=in_app.lease_expires_at,
            claim_token=in_app.claim_token,
        )
        confirmed_at = in_app.created_at + timedelta(minutes=1)
        confirmed = repository.confirm_preparing(
            identity.business_id,
            identity.company_id,
            in_app.id,
            in_app.claim_token,
            confirmed_at,
            _cadence(confirmed_at),
            identity.owner_user_id,
        )
        assert (
            confirmed.status.value,
            confirmed.presented_at,
            confirmed.settled_at,
        ) == (
            "confirmed",
            confirmed_at,
            confirmed_at,
        )
        assert not repository.release_expired_preparing(
            identity.business_id,
            identity.company_id,
            in_app.id,
            confirmed_at + timedelta(days=1),
        )

        failed = draft("pre-send-failure", confirmed_at)
        repository.acquire_preparing(
            failed,
            now=failed.created_at,
            lease_expires_at=failed.lease_expires_at,
            claim_token=failed.claim_token,
        )
        started_at = failed.created_at + timedelta(minutes=1)
        repository.mark_sending(
            identity.business_id,
            identity.company_id,
            failed.id,
            failed.claim_token,
            started_at,
            _cadence(started_at),
        )
        failed_at = started_at + timedelta(minutes=1)
        abandoned = repository.settle_sending(
            identity.business_id,
            identity.company_id,
            failed.id,
            failed.claim_token,
            "pre_send_failed",
            failed_at,
        )
        assert (
            abandoned.status.value,
            abandoned.settled_at,
            abandoned.presented_at,
        ) == (
            "abandoned",
            failed_at,
            None,
        )
        with pytest.raises(ConflictError):
            repository.settle_sending(
                identity.business_id,
                identity.company_id,
                failed.id,
                failed.claim_token,
                "unknown",
                failed_at + timedelta(minutes=1),
            )
        assert not repository.release_expired_preparing(
            identity.business_id,
            identity.company_id,
            failed.id,
            failed_at + timedelta(days=1),
        )

        successful = draft("sending-confirmed", failed_at)
        repository.acquire_preparing(
            successful,
            now=successful.created_at,
            lease_expires_at=successful.lease_expires_at,
            claim_token=successful.claim_token,
        )
        smtp_started_at = successful.created_at + timedelta(minutes=1)
        repository.mark_sending(
            identity.business_id,
            identity.company_id,
            successful.id,
            successful.claim_token,
            smtp_started_at,
            _cadence(smtp_started_at),
        )
        smtp_accepted_at = smtp_started_at + timedelta(seconds=20)
        result_observed_at = smtp_started_at + timedelta(seconds=45)
        sent = repository.settle_sending(
            identity.business_id,
            identity.company_id,
            successful.id,
            successful.claim_token,
            "confirmed",
            result_observed_at,
            smtp_accepted_at,
        )
        assert (
            sent.status.value,
            sent.presented_at,
            sent.settled_at,
        ) == ("confirmed", smtp_accepted_at, result_observed_at)

        claim = draft("same-key-intent", result_observed_at)
        repository.acquire_preparing(
            claim,
            now=claim.created_at,
            lease_expires_at=claim.lease_expires_at,
            claim_token=claim.claim_token,
        )
        with pytest.raises(ConflictError), connection.transaction():
            altered = draft("same-key-intent", result_observed_at)
            altered = OfferCycle(
                **{**altered.__dict__, "payload_fingerprint": "c" * 64}
            )
            repository.acquire_preparing(
                altered,
                now=result_observed_at,
                lease_expires_at=result_observed_at + timedelta(minutes=5),
                claim_token="different-intent-token",
            )
        with pytest.raises(ConflictError), connection.transaction():
            repository.acquire_preparing(
                draft("different-key-same-company", result_observed_at),
                now=result_observed_at,
                lease_expires_at=result_observed_at + timedelta(minutes=5),
                claim_token="different-company-claim",
            )
        assert (
            repository.get_by_request_key(identity.business_id, claim.idempotency_key)
            == claim
        )
        assert (
            repository.get_pending(identity.business_id, identity.company_id) == claim
        )
        sending = repository.mark_sending(
            identity.business_id,
            identity.company_id,
            claim.id,
            claim.claim_token,
            result_observed_at + timedelta(minutes=1),
            _cadence(result_observed_at + timedelta(minutes=1)),
        )
        assert sending.status.value == "sending"
        assert not repository.release_expired_preparing(
            identity.business_id,
            identity.company_id,
            claim.id,
            claim.lease_expires_at + timedelta(days=1),
        )

        persisted_cycles = connection.execute(
            "SELECT id,status FROM operational.offer_cycles WHERE business_id=%s",
            (identity.business_id,),
        ).fetchall()
        assert dict(persisted_cycles) == {
            expired.id: "abandoned",
            explicit.id: "abandoned",
            in_app.id: "confirmed",
            failed.id: "abandoned",
            successful.id: "confirmed",
            claim.id: "sending",
        }
        event_kinds = connection.execute(
            "SELECT event_kind FROM operational.offer_cycle_events "
            "WHERE business_id=%s",
            (identity.business_id,),
        ).fetchall()
        assert Counter(row[0] for row in event_kinds) == Counter(
            {
                "preparing_acquired": 6,
                "preparing_expired": 1,
                "preparing_abandoned": 1,
                "preparing_confirmed": 1,
                "sending_authorized": 3,
                "sending_failed": 1,
                "sending_confirmed": 1,
            }
        )


def test_cycle_and_acquisition_event_rollback_together_without_repository_commit(
    management_database_url,
):
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendation = PostgresRecommendationRepository(session).create_open(
            valid_recommendation(identity, at=now)
        )
        revision = PostgresAssessmentRevisionRepository(session).append(
            valid_assessment_revision(identity, recommendation, at=now)
        )
        connection.commit()
        cycle_id = uuid4()
        cycle = OfferCycle(
            id=cycle_id,
            business_id=identity.business_id,
            company_id=identity.company_id,
            recommendation_id=recommendation.id,
            selected_revision_id=revision.id,
            idempotency_key="rollback-with-event",
            payload_fingerprint="d" * 64,
            status=OfferCycleStatus("preparing"),
            created_at=now,
            updated_at=now,
            claim_token="rollback-claim",
            lease_expires_at=now + timedelta(minutes=5),
        )
        repository = PostgresOfferCycleRepository(session)
        with (
            pytest.raises(RuntimeError, match="simulate caller rollback"),
            connection.transaction(),
        ):
            repository.acquire_preparing(
                cycle,
                now=now,
                lease_expires_at=cycle.lease_expires_at,
                claim_token=cycle.claim_token,
            )
            raise RuntimeError("simulate caller rollback")

    with psycopg.connect(management_database_url) as observer:
        assert observer.execute(
            "SELECT (SELECT COUNT(*) FROM operational.offer_cycles WHERE id=%s), "
            "(SELECT COUNT(*) FROM operational.offer_cycle_events WHERE offer_cycle_id=%s)",
            (cycle_id, cycle_id),
        ).fetchone() == (0, 0)
