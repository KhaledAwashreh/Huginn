from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from itertools import count

import psycopg
import pytest

from huginn.management.application.requests.confirm_recommendation_offer_request import (
    ConfirmRecommendationOfferRequest,
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
from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.confirm_recommendation_offer_service import (
    ConfirmRecommendationOfferService,
)
from huginn.management.application.services.later_recommendation_service import (
    LaterRecommendationService,
)
from huginn.management.application.services.mark_recommendation_not_relevant_service import (
    MarkRecommendationNotRelevantService,
)
from huginn.management.application.services.prepare_recommendation_offer_service import (
    PrepareRecommendationOfferService,
)
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.pause_choice import PauseChoice
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)
from tests.management.persistence.retained_prospecting_fixtures import (
    generate_retained_brightroom_selection,
    seed_retained_brightroom_context,
)


def _services(context):
    sequence = count()
    prepare = PrepareRecommendationOfferService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: context.current_time[0],
        token_factory=lambda: f"retained-claim-{next(sequence)}",
    )
    confirm = ConfirmRecommendationOfferService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: context.current_time[0],
    )
    return prepare, confirm


def test_prepare_confirm_concurrency_expiry_and_fresh_revision_requirement(
    retained_management_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selected = generate_retained_brightroom_selection(context)
    prepare, confirm = _services(context)
    request = PrepareRecommendationOfferRequest(
        selected.recommendation_id,
        selected.revision_id,
        f"same-key-{context.suffix}",
    )

    # Two same-key requests racing under separate database connections replay
    # one claim, rather than creating two cycles or exposing two tokens.
    with ThreadPoolExecutor(max_workers=2) as pool:
        prepared_values = list(
            pool.map(lambda _: prepare.execute(context.principal, request), range(2))
        )
    prepared = prepared_values[0]
    assert prepared_values == [prepared, prepared]
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycles "
                "WHERE business_id=%s AND idempotency_key=%s",
                (context.business_id, request.request_key),
            ).fetchone()[0]
            == 1
        )

    # An expired claim is abandoned, loses its token, and cannot be confirmed.
    # A distinct fresh key can acquire a replacement claim for the same exact
    # selected revision because expiry did not create exposure or cooldown.
    context.current_time[0] = prepared.lease_expires_at
    context.current_time[0] += timedelta(seconds=1)
    with psycopg.connect(context.database_url) as connection:
        original_company_name = connection.execute(
            "SELECT name FROM gold.company WHERE id=%s", (context.company_id,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE gold.company SET name=%s WHERE id=%s",
            (f"{original_company_name} changed", context.company_id),
        )
        connection.commit()
    stale_new_key = PrepareRecommendationOfferRequest(
        selected.recommendation_id,
        selected.revision_id,
        f"stale-new-key-{context.suffix}",
    )
    with pytest.raises(ConflictError):
        prepare.execute(context.principal, stale_new_key)
    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT status,claim_token FROM operational.offer_cycles WHERE id=%s",
            (prepared.offer_cycle_id,),
        ).fetchone() == ("abandoned", None)
        connection.execute(
            "UPDATE gold.company SET name=%s WHERE id=%s",
            (original_company_name, context.company_id),
        )
        connection.commit()
    renewed_requests = tuple(
        PrepareRecommendationOfferRequest(
            selected.recommendation_id,
            selected.revision_id,
            f"new-key-{attempt}-{context.suffix}",
        )
        for attempt in (1, 2)
    )

    def try_prepare(request):
        try:
            return prepare.execute(context.principal, request)
        except ConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        renewal_results = list(pool.map(try_prepare, renewed_requests))
    renewed_values = [value for value in renewal_results if value is not None]
    assert len(renewed_values) == 1
    renewed = renewed_values[0]
    assert renewed.status.value == "preparing"
    assert prepare.execute(context.principal, request).status.value == "abandoned"
    with pytest.raises(ConflictError):
        confirm.execute(
            context.principal,
            ConfirmRecommendationOfferRequest(
                prepared.offer_cycle_id, prepared.claim_token
            ),
        )
    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT status,claim_token FROM operational.offer_cycles WHERE id=%s",
            (prepared.offer_cycle_id,),
        ).fetchone() == ("abandoned", None)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 0
        )

    # Concurrent confirms replay the one committed first presentation and
    # append exactly one cooldown/event pair.
    context.current_time[0] += timedelta(seconds=1)
    confirm_request = ConfirmRecommendationOfferRequest(
        renewed.offer_cycle_id, renewed.claim_token
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        confirmed_values = list(
            pool.map(
                lambda _: confirm.execute(context.principal, confirm_request), range(2)
            )
        )
    assert confirmed_values[0] == confirmed_values[1]
    confirmed = confirmed_values[0]
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycle_events "
                "WHERE offer_cycle_id=%s AND event_kind='preparing_confirmed'",
                (renewed.offer_cycle_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 1
        )

    # A revision assessed before the previous cadence expires is no longer a
    # valid offer. A fresh explicit run creates a new selected revision.
    context.current_time[0] = confirmed.cooldown_expires_at
    context.current_time[0] += timedelta(seconds=1)
    with pytest.raises(ConflictError):
        prepare.execute(
            context.principal,
            PrepareRecommendationOfferRequest(
                selected.recommendation_id,
                selected.revision_id,
                f"stale-after-cooldown-{context.suffix}",
            ),
        )
    fresh = generate_retained_brightroom_selection(context)
    assert fresh.recommendation_id == selected.recommendation_id
    assert fresh.revision_id != selected.revision_id
    fresh_claim = prepare.execute(
        context.principal,
        PrepareRecommendationOfferRequest(
            fresh.recommendation_id,
            fresh.revision_id,
            f"fresh-after-cooldown-{context.suffix}",
        ),
    )
    assert fresh_claim.status.value == "preparing"
    context.current_time[0] += timedelta(seconds=1)
    second_presentation = confirm.execute(
        context.principal,
        ConfirmRecommendationOfferRequest(
            fresh_claim.offer_cycle_id, fresh_claim.claim_token
        ),
    )
    assert second_presentation.assessment_revision_id == fresh.revision_id
    assert second_presentation.presented_at > confirmed.presented_at
    assert second_presentation.cooldown_expires_at == (
        second_presentation.presented_at + timedelta(days=30)
    )
    with psycopg.connect(context.database_url) as connection:
        first_presented_at = connection.execute(
            "SELECT first_presented_at FROM operational.recommendations WHERE id=%s",
            (selected.recommendation_id,),
        ).fetchone()[0]
        cycles = connection.execute(
            "SELECT selected_revision_id,status,presented_at FROM operational.offer_cycles "
            "WHERE recommendation_id=%s ORDER BY created_at,id",
            (selected.recommendation_id,),
        ).fetchall()
        cooldowns = connection.execute(
            "SELECT effective_at,expires_at FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s AND kind='cooldown' "
            "ORDER BY effective_at,id",
            (context.business_id, context.company_id),
        ).fetchall()
    assert first_presented_at == confirmed.presented_at
    assert cycles == [
        (selected.revision_id, "abandoned", None),
        (selected.revision_id, "confirmed", confirmed.presented_at),
        (fresh.revision_id, "confirmed", second_presentation.presented_at),
    ]
    assert cooldowns == [
        (
            confirmed.presented_at,
            confirmed.cooldown_expires_at,
        ),
        (
            second_presentation.presented_at,
            second_presentation.cooldown_expires_at,
        ),
    ]


@pytest.mark.parametrize(
    "intervening_command", ("save", "reject", "later", "profile_edit")
)
def test_user_decision_before_confirmation_wins(
    retained_management_database_url, monkeypatch, intervening_command
):
    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selected = generate_retained_brightroom_selection(context)
    prepare, confirm = _services(context)
    claim = prepare.execute(
        context.principal,
        PrepareRecommendationOfferRequest(
            selected.recommendation_id,
            selected.revision_id,
            f"decision-race-{context.suffix}",
        ),
    )
    command_time = context.current_time[0]

    def work_factory():
        return PostgresProspectingUnitOfWork(context.connection_factory)

    if intervening_command == "save":
        SaveRecommendationService(work_factory, clock=lambda: command_time).execute(
            context.principal,
            SaveRecommendationRequest(
                selected.recommendation_id,
                selected.revision_id,
                f"save-{context.suffix}",
            ),
        )
    elif intervening_command == "reject":
        with PostgresProspectingUnitOfWork(
            context.connection_factory, read_only=True
        ) as work:
            recommendation = work.recommendations.get_owned(
                context.business_id, selected.recommendation_id
            )
        assert recommendation is not None
        MarkRecommendationNotRelevantService(
            work_factory, clock=lambda: command_time
        ).execute(
            context.principal,
            MarkRecommendationNotRelevantRequest(
                selected.recommendation_id,
                selected.revision_id,
                recommendation.version,
                f"reject-{context.suffix}",
            ),
        )
    elif intervening_command == "later":
        with PostgresProspectingUnitOfWork(
            context.connection_factory, read_only=True
        ) as work:
            recommendation = work.recommendations.get_owned(
                context.business_id, selected.recommendation_id
            )
            preferences = work.business_recommendation_preferences.get(
                context.business_id
            )
        assert recommendation is not None and preferences is not None
        LaterRecommendationService(work_factory, clock=lambda: command_time).execute(
            context.principal,
            LaterRecommendationRequest(
                selected.recommendation_id,
                selected.revision_id,
                recommendation.version,
                PauseChoice("x1"),
                preferences.repeat_interval_days,
                preferences.updated_at,
                None,
                None,
                f"later-{context.suffix}",
            ),
        )
    else:
        with psycopg.connect(context.database_url) as connection:
            connection.execute(
                "UPDATE operational.professional_profiles SET headline=%s "
                "WHERE user_id=%s",
                ("Changed after assessment", context.owner_user_id),
            )
            connection.commit()

    with pytest.raises(ConflictError):
        confirm.execute(
            context.principal,
            ConfirmRecommendationOfferRequest(claim.offer_cycle_id, claim.claim_token),
        )
    with psycopg.connect(context.database_url) as connection:
        assert (
            connection.execute(
                "SELECT status FROM operational.offer_cycles WHERE id=%s",
                (claim.offer_cycle_id,),
            ).fetchone()[0]
            == "preparing"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 0
        )
        if intervening_command == "profile_edit":
            current_headline, old_snapshot = connection.execute(
                "SELECT profile.headline,revision.professional_profile_snapshot "
                "FROM operational.professional_profiles AS profile "
                "JOIN operational.assessment_revisions AS revision "
                "ON revision.id=%s WHERE profile.user_id=%s",
                (selected.revision_id, context.owner_user_id),
            ).fetchone()
            assert current_headline == "Changed after assessment"
            assert old_snapshot["headline"] == "Independent career coach"


def test_generation_commits_expiry_cleanup_before_lost_evidence_selection(
    retained_management_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selected = generate_retained_brightroom_selection(context)
    prepare, _ = _services(context)
    claim = prepare.execute(
        context.principal,
        PrepareRecommendationOfferRequest(
            selected.recommendation_id,
            selected.revision_id,
            f"lost-evidence-{context.suffix}",
        ),
    )
    context.current_time[0] = claim.lease_expires_at + timedelta(seconds=1)
    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company_signal SET company_id=%s "
            "WHERE source='eu_startups' AND source_stable_id=%s",
            (context.guard_company_id, context.stable_id),
        )
        connection.commit()

    context.generation_service.execute_weekly(context.business_id)

    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT status,claim_token FROM operational.offer_cycles WHERE id=%s",
            (claim.offer_cycle_id,),
        ).fetchone() == ("abandoned", None)
        assert connection.execute(
            "SELECT event_kind,actor_user_id FROM operational.offer_cycle_events "
            "WHERE offer_cycle_id=%s ORDER BY recorded_at,id",
            (claim.offer_cycle_id,),
        ).fetchall() == [
            ("preparing_acquired", None),
            ("preparing_expired", None),
        ]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
                (context.business_id, context.company_id),
            ).fetchone()[0]
            == 0
        )
