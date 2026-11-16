from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.requests.cancel_recommendation_pause_request import (
    CancelRecommendationPauseRequest,
)
from huginn.management.application.requests.later_recommendation_request import (
    LaterRecommendationRequest,
)
from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.application.requests.reverse_recommendation_rejection_request import (
    ReverseRecommendationRejectionRequest,
)
from huginn.management.application.services.cancel_recommendation_pause_service import (
    CancelRecommendationPauseService,
)
from huginn.management.application.services.later_recommendation_service import (
    LaterRecommendationService,
)
from huginn.management.application.services.mark_recommendation_not_relevant_service import (
    MarkRecommendationNotRelevantService,
)
from huginn.management.application.services.reverse_recommendation_rejection_service import (
    ReverseRecommendationRejectionService,
)
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.pause_choice import PauseChoice
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
    PsycopgDatabaseSession,
)
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.repositories.suppression_block import (
    PostgresSuppressionBlockRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
)

# Seed factories timestamp from the wall clock; keep command fixtures later than
# those generated rows so database monotonic-time guards are exercised honestly.
NOW = datetime.now(UTC) + timedelta(days=1)


def _factory(database_url):
    return ManagementConnectionFactory(database_url, statement_timeout_ms=5000)


def _setup(database_url):
    with psycopg.connect(database_url) as connection:
        identity, recommendation, revision = seed_owned_recommendation_revision(
            connection
        )
    return identity, recommendation, revision


def _principal(identity):
    return Principal(identity.account_id, identity.owner_user_id)


def _append_block(database_url, identity, kind, *, expires_at, created_at=NOW):
    block = SuppressionBlock(
        id=uuid4(),
        business_id=identity.business_id,
        company_id=identity.company_id,
        kind=SuppressionKind(kind),
        created_at=created_at,
        effective_at=created_at,
        created_by_user_id=identity.owner_user_id
        if kind in {"pause", "rejection"}
        else None,
        expires_at=expires_at,
        reason="Retained fixture reason" if kind in {"pause", "rejection"} else None,
    )
    with psycopg.connect(database_url) as connection:
        PostgresSuppressionBlockRepository(PsycopgDatabaseSession(connection)).append(
            block
        )
    return block


def _later_request(
    recommendation,
    revision,
    preferences,
    *,
    key,
    pause,
    choice="x2",
):
    return LaterRecommendationRequest(
        recommendation_id=recommendation.id,
        assessment_revision_id=revision.id,
        expected_recommendation_version=recommendation.version,
        pause_choice=PauseChoice(choice),
        expected_repeat_interval_days=preferences.repeat_interval_days,
        expected_preference_updated_at=preferences.updated_at,
        expected_pause_id=pause.id if pause else None,
        expected_pause_version=pause.version if pause else None,
        request_key=key,
    )


def test_rejection_and_reversal_are_attributed_atomic_repeat_safe_and_preserve_other_blocks(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    cooldown = _append_block(
        management_database_url,
        identity,
        "cooldown",
        expires_at=NOW + timedelta(days=4),
    )
    pause = _append_block(
        management_database_url,
        identity,
        "pause",
        expires_at=NOW + timedelta(days=8),
    )
    principal = _principal(identity)
    reject = MarkRecommendationNotRelevantService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: NOW + timedelta(minutes=2),
    )
    request = MarkRecommendationNotRelevantRequest(
        recommendation.id,
        revision.id,
        recommendation.version,
        "reject-current",
        "Not a buyer",
    )
    result = reject.execute(principal, request)
    assert reject.execute(principal, request) == result

    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT status,version,resolved_by_user_id,resolved_at,resolution_reason "
            "FROM operational.recommendations WHERE id=%s",
            (recommendation.id,),
        ).fetchone() == (
            "rejected",
            recommendation.version + 1,
            identity.owner_user_id,
            NOW + timedelta(minutes=2),
            "not_relevant: Not a buyer",
        )
        rejection = connection.execute(
            "SELECT id,business_id,company_id,kind,created_by_user_id,reason,"
            "expires_at,version FROM operational.suppression_blocks "
            "WHERE id=%s",
            (result.suppression_block_id,),
        ).fetchone()
        assert rejection == (
            result.suppression_block_id,
            identity.business_id,
            identity.company_id,
            "rejection",
            identity.owner_user_id,
            "Not a buyer",
            None,
            1,
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND idempotency_key=%s",
                (identity.business_id, "reject-current"),
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

    reverse = ReverseRecommendationRejectionService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: NOW + timedelta(minutes=4),
    )
    reverse_request = ReverseRecommendationRejectionRequest(
        result.suppression_block_id, 1, "reverse-current"
    )
    reversed_result = reverse.execute(principal, reverse_request)
    assert reverse.execute(principal, reverse_request) == reversed_result

    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT status,version,resolved_by_user_id,resolved_at,resolution_reason "
            "FROM operational.recommendations WHERE id=%s",
            (recommendation.id,),
        ).fetchone() == (
            "rejected",
            recommendation.version + 1,
            identity.owner_user_id,
            NOW + timedelta(minutes=2),
            "not_relevant: Not a buyer",
        )
        assert connection.execute(
            "SELECT version,cleared_at,cleared_by_user_id "
            "FROM operational.suppression_blocks WHERE id=%s",
            (result.suppression_block_id,),
        ).fetchone() == (2, NOW + timedelta(minutes=4), identity.owner_user_id)
        assert connection.execute(
            "SELECT cleared_at,version FROM operational.suppression_blocks WHERE id=%s",
            (cooldown.id,),
        ).fetchone() == (None, 1)
        assert connection.execute(
            "SELECT cleared_at,version FROM operational.suppression_blocks WHERE id=%s",
            (pause.id,),
        ).fetchone() == (None, 1)


def test_later_replaces_one_pause_keeps_history_and_replays_exact_receipt(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    old_pause = _append_block(
        management_database_url,
        identity,
        "pause",
        expires_at=NOW + timedelta(days=10),
    )
    service = LaterRecommendationService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: NOW + timedelta(minutes=3),
    )
    with psycopg.connect(management_database_url) as connection:
        preferences = connection.execute(
            "SELECT repeat_interval_days,updated_at "
            "FROM operational.business_recommendation_preferences "
            "WHERE business_id=%s",
            (identity.business_id,),
        ).fetchone()
    from huginn.management.domain.entities.business_recommendation_preferences import (
        BusinessRecommendationPreferences,
    )
    from huginn.management.domain.value_objects.business_recommendation_preferences import (
        BusinessRecommendationPreferencesChanges,
    )

    preference = BusinessRecommendationPreferences(
        identity.business_id, preferences[0], preferences[1]
    )
    request = _later_request(
        recommendation,
        revision,
        preference,
        key="later-replace",
        pause=old_pause,
    )
    result = service.execute(_principal(identity), request)
    assert service.execute(_principal(identity), request) == result
    assert result.pause_choice == "x2"
    assert result.repeat_interval_days == preference.repeat_interval_days
    assert result.expires_at == NOW + timedelta(minutes=3) + timedelta(
        days=2 * preference.repeat_interval_days
    )

    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT cleared_at,cleared_by_user_id,version FROM "
            "operational.suppression_blocks WHERE id=%s",
            (old_pause.id,),
        ).fetchone() == (NOW + timedelta(minutes=3), identity.owner_user_id, 2)
        assert connection.execute(
            "SELECT kind,created_by_user_id,created_at,expires_at,version "
            "FROM operational.suppression_blocks WHERE id=%s",
            (result.suppression_block_id,),
        ).fetchone() == (
            "pause",
            identity.owner_user_id,
            NOW + timedelta(minutes=3),
            result.expires_at,
            1,
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='pause'",
                (identity.business_id, identity.company_id),
            ).fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT status FROM operational.recommendations WHERE id=%s",
                (recommendation.id,),
            ).fetchone()[0]
            == "open"
        )

        with PostgresProspectingUnitOfWork(_factory(management_database_url)) as work:
            changed = work.business_recommendation_preferences.update(
                identity.business_id, BusinessRecommendationPreferencesChanges(45)
            )
            assert changed is not None
            work.commit()

    stale_base = _later_request(
        recommendation,
        revision,
        preference,
        key="later-stale-base",
        pause=None,
        choice="x1",
    )
    with pytest.raises(ConflictError):
        service.execute(_principal(identity), stale_base)
    stale_pause = _later_request(
        recommendation,
        revision,
        changed,
        key="later-stale-pause",
        pause=old_pause,
        choice="x1",
    )
    with pytest.raises(ConflictError):
        service.execute(_principal(identity), stale_pause)
    with psycopg.connect(management_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='pause'",
                (identity.business_id, identity.company_id),
            ).fetchone()[0]
            == 2
        )


def test_pause_cancellation_clears_only_selected_block_and_keeps_history(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    pause = _append_block(
        management_database_url,
        identity,
        "pause",
        expires_at=NOW + timedelta(days=10),
    )
    rejection = _append_block(
        management_database_url,
        identity,
        "rejection",
        expires_at=None,
    )
    service = CancelRecommendationPauseService(
        lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
        clock=lambda: NOW + timedelta(minutes=5),
    )
    request = CancelRecommendationPauseRequest(pause.id, 1, "cancel-pause")
    response = service.execute(_principal(identity), request)
    assert service.execute(_principal(identity), request) == response
    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT cleared_at,cleared_by_user_id,version FROM "
            "operational.suppression_blocks WHERE id=%s",
            (pause.id,),
        ).fetchone() == (NOW + timedelta(minutes=5), identity.owner_user_id, 2)
        assert connection.execute(
            "SELECT cleared_at,version FROM operational.suppression_blocks WHERE id=%s",
            (rejection.id,),
        ).fetchone() == (None, 1)
        assert connection.execute(
            "SELECT status,resolved_at,resolution_reason FROM "
            "operational.recommendations WHERE id=%s",
            (recommendation.id,),
        ).fetchone() == ("open", None, None)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND idempotency_key=%s",
                (identity.business_id, request.request_key),
            ).fetchone()[0]
            == 1
        )


class _FailingCommands:
    def __init__(self, delegate):
        self._delegate = delegate

    def get_by_key(self, business_id, key):
        return self._delegate.get_by_key(business_id, key)

    def record(self, receipt):
        raise ConflictError("simulated receipt write failure")


class _FailingReceiptUnitOfWork(PostgresProspectingUnitOfWork):
    def __enter__(self):
        super().__enter__()
        self.commands = _FailingCommands(self.commands)
        return self


def test_rejection_receipt_failure_rolls_back_resolution_and_block(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    service = MarkRecommendationNotRelevantService(
        lambda: _FailingReceiptUnitOfWork(_factory(management_database_url)),
        clock=lambda: NOW + timedelta(minutes=2),
    )

    with pytest.raises(ConflictError, match="simulated receipt write failure"):
        service.execute(
            _principal(identity),
            MarkRecommendationNotRelevantRequest(
                recommendation.id,
                revision.id,
                recommendation.version,
                "reject-rollback",
                "Do not fit",
            ),
        )

    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT status,version,resolved_at,resolution_reason "
            "FROM operational.recommendations WHERE id=%s",
            (recommendation.id,),
        ).fetchone() == ("open", recommendation.version, None, None)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='rejection'",
                (identity.business_id, identity.company_id),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND idempotency_key=%s",
                (identity.business_id, "reject-rollback"),
            ).fetchone()[0]
            == 0
        )


def test_two_concurrent_later_commands_cannot_replace_the_same_expected_pause_twice(
    management_database_url,
):
    identity, recommendation, revision = _setup(management_database_url)
    old_pause = _append_block(
        management_database_url,
        identity,
        "pause",
        expires_at=NOW + timedelta(days=10),
    )
    with psycopg.connect(management_database_url) as connection:
        preferences = connection.execute(
            "SELECT repeat_interval_days,updated_at "
            "FROM operational.business_recommendation_preferences "
            "WHERE business_id=%s",
            (identity.business_id,),
        ).fetchone()
    from huginn.management.domain.entities.business_recommendation_preferences import (
        BusinessRecommendationPreferences,
    )

    preference = BusinessRecommendationPreferences(
        identity.business_id, preferences[0], preferences[1]
    )
    barrier = Barrier(2, timeout=5)

    def run(index):
        request = _later_request(
            recommendation,
            revision,
            preference,
            key=f"later-race-{index}",
            pause=old_pause,
            choice="x1" if index == 0 else "x3",
        )
        service = LaterRecommendationService(
            lambda: PostgresProspectingUnitOfWork(_factory(management_database_url)),
            clock=lambda: NOW + timedelta(minutes=3),
        )
        barrier.wait()
        try:
            return ("ok", service.execute(_principal(identity), request))
        except ConflictError:
            return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(run, range(2)))
    assert sorted(outcome[0] for outcome in outcomes) == ["conflict", "ok"]
    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT cleared_at,version FROM operational.suppression_blocks WHERE id=%s",
            (old_pause.id,),
        ).fetchone() == (NOW + timedelta(minutes=3), 2)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='pause' "
                "AND cleared_at IS NULL",
                (identity.business_id, identity.company_id),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND scope='later_recommendation'",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )
