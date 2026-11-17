from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.errors.errors import RateLimitError
from huginn.management.application.requests.confirm_recommendation_offer_request import (
    ConfirmRecommendationOfferRequest,
)
from huginn.management.application.requests.generate_recommendations_request import (
    GenerateRecommendationsRequest,
)
from huginn.management.application.requests.prepare_recommendation_offer_request import (
    PrepareRecommendationOfferRequest,
)
from huginn.management.application.services.recommendation_generation import (
    RecommendationGenerationService,
)
from huginn.management.application.services.recommendation_offer_service import (
    RecommendationOfferService,
)
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.database.client import (
    PsycopgDatabaseSession,
)
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)
from huginn.management.persistence.repositories.suppression_block import (
    PostgresSuppressionBlockRepository,
)
from tests.management.persistence.retained_prospecting_fixtures import (
    seed_retained_brightroom_context,
)


def test_retained_brightroom_generates_shared_revision_with_currentness_and_quota_guards(
    retained_management_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    url = context.database_url
    suffix = context.suffix
    stable_id = context.stable_id
    account_id = context.account_id
    owner = context.owner_user_id
    business_id = context.business_id
    company_id = context.company_id
    strategy_id = context.strategy_id
    second_strategy_id = context.second_strategy_id
    guard_company_id = context.guard_company_id
    account_before = context.account_before
    user_before = context.user_before
    personal_profile_before = context.personal_profile_before
    preferences_before = context.preferences_before
    configuration_before = context.configuration_before
    factory = context.connection_factory
    current_time = context.current_time
    service = context.generation_service
    read_service = context.read_service
    principal = context.principal

    # A known current mismatch is never offered or persisted as an occurrence.
    service.execute(principal, GenerateRecommendationsRequest(strategy_id))
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendations "
                "WHERE business_id=%s AND company_id=%s",
                (business_id, company_id),
            ).fetchone()[0]
            == 0
        )

        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s", (company_id,)
        )
        connection.commit()

    # The source listing can disappear after selection but before pair locking.
    # Final source revalidation must drop it without creating an occurrence.
    class _SourceRaceUnitOfWork:
        def __init__(self):
            self.work = PostgresProspectingUnitOfWork(factory)
            self.injected = False

        def __enter__(self):
            self.work.__enter__()
            return self

        def __exit__(self, *args):
            return self.work.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.work, name)

        def lock_business_company(self, locked_business_id, locked_company_id):
            self.work.lock_business_company(locked_business_id, locked_company_id)
            if not self.injected and locked_company_id == company_id:
                with psycopg.connect(url) as connection:
                    connection.execute(
                        "UPDATE gold.company_signal SET company_id=%s "
                        "WHERE source='eu_startups' AND source_stable_id=%s",
                        (guard_company_id, stable_id),
                    )
                self.injected = True

    racing_service = RecommendationGenerationService(
        _SourceRaceUnitOfWork,
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: current_time[0],
    )
    raced = racing_service.execute(
        principal, GenerateRecommendationsRequest(strategy_id)
    )
    assert raced.references == ()
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendations WHERE business_id=%s",
                (business_id,),
            ).fetchone()[0]
            == 0
        )
        connection.execute(
            "UPDATE gold.company_signal SET company_id=%s "
            "WHERE source='eu_startups' AND source_stable_id=%s",
            (company_id, stable_id),
        )
        connection.commit()

    # A pause committed after assessment and effective before finalization must
    # suppress the selected company at the post-lock recheck time.
    block_id = uuid4()

    class _DecisionRaceUnitOfWork(_SourceRaceUnitOfWork):
        def lock_business_company(self, locked_business_id, locked_company_id):
            self.work.lock_business_company(locked_business_id, locked_company_id)
            if not self.injected and locked_company_id == company_id:
                recorded_at = current_time[0] + timedelta(seconds=1)
                with psycopg.connect(url) as connection:
                    PostgresSuppressionBlockRepository(
                        PsycopgDatabaseSession(connection)
                    ).append(
                        SuppressionBlock(
                            block_id,
                            business_id,
                            company_id,
                            SuppressionKind("pause"),
                            recorded_at,
                            created_by_user_id=owner,
                            expires_at=recorded_at + timedelta(days=1),
                            reason="intervening decision regression",
                        )
                    )
                    connection.commit()
                current_time[0] += timedelta(seconds=2)
                self.injected = True

    decision_race_service = RecommendationGenerationService(
        _DecisionRaceUnitOfWork,
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: current_time[0],
    )
    decision_raced = decision_race_service.execute(
        principal, GenerateRecommendationsRequest(strategy_id)
    )
    assert decision_raced.references == ()
    with psycopg.connect(url) as connection:
        PostgresSuppressionBlockRepository(
            PsycopgDatabaseSession(connection)
        ).clear_one(
            business_id,
            company_id,
            block_id,
            1,
            owner,
            current_time[0],
        )
        connection.commit()

    # The retained source category resolves the missing country; the real source
    # payload, currentness row and normalized observation drive a complete revision.
    current_time[0] += timedelta(minutes=16)
    current_time[0] += timedelta(seconds=1)
    generated = service.execute(principal, GenerateRecommendationsRequest(strategy_id))
    target_recommendation_id = None
    with psycopg.connect(url) as connection:
        target_recommendation_id = connection.execute(
            "SELECT id FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s AND status='open'",
            (business_id, company_id),
        ).fetchone()[0]
    target = next(
        value
        for value in generated.references
        if value.recommendation_id == target_recommendation_id
    )
    with PostgresProspectingUnitOfWork(factory, read_only=True) as work:
        recommendation = work.recommendations.get_owned(
            business_id, target.recommendation_id
        )
        revision = work.assessment_revisions.get_owned(
            business_id, target.recommendation_id, target.revision_id
        )
        assert recommendation.current_revision_id == target.revision_id
        assert len(revision.strategy_assessments) == 1
        assert revision.strategy_assessments[0].strategy_id == strategy_id
        assert (
            revision.professional_profile_snapshot.to_json_object()
            == personal_profile_before
        )
        assert "coaching, marketplace" in " ".join(
            item.to_json_object()["description"] for item in revision.evidence_snapshots
        )
        assert revision.evidence_observation_ids
        assert revision.policy_versions == (
            "company-fit-v1",
            "research-ranking-v1",
            "topic-overlap-v2",
        )
        assert revision.strategy_assessments[0].assessment_snapshot.value[
            "evaluation_seed"
        ]
        current_source = PostgresRecommendationGenerationSource(work.connection)
        assert (
            current_source.current_company_for_revision(revision, current_time[0])
            is not None
        )
        company_facts = revision.strategy_assessments[0].assessment_snapshot.value[
            "company_facts"
        ]
        assert company_facts["raw_country"] is None
        assert company_facts["resolved_country"] == "DE"
        assert company_facts["country_evidence_label"] == "Germany"
        assert company_facts["country_evidence_id"] in {
            evidence.to_json_object()["observation_id"]
            for evidence in revision.evidence_snapshots
        }
    first_view = read_service.get_recommendation(
        principal,
        target.recommendation_id,
        assessment_revision_id=target.revision_id,
    )
    assert first_view.assessment == revision
    assert first_view.evidence_state == "current"
    assert first_view.current_eligibility == "not_reassessed"

    # Weekly uses all valid active manual strategies and persists each score and
    # association separately on the same shared occurrence.
    current_time[0] += timedelta(seconds=1)
    weekly = service.execute_weekly(business_id)
    weekly_target = next(
        value
        for value in weekly.references
        if value.recommendation_id == target.recommendation_id
    )
    with PostgresProspectingUnitOfWork(factory, read_only=True) as work:
        weekly_revision = work.assessment_revisions.get_owned(
            business_id, target.recommendation_id, weekly_target.revision_id
        )
        assert {
            value.strategy_id for value in weekly_revision.strategy_assessments
        } == {strategy_id, second_strategy_id}
        weekly_scores = [
            value.assessment_snapshot.value["score"]
            for value in weekly_revision.strategy_assessments
        ]
        assert len(weekly_scores) == 2
        assert all(type(score) is int and 0 <= score <= 100 for score in weekly_scores)

    # Same-pair concurrent requests serialize and append revisions to one stable
    # open occurrence, rather than creating separate channel identities.
    current_time[0] += timedelta(seconds=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: service.execute(
                    principal, GenerateRecommendationsRequest(strategy_id)
                ),
                range(2),
            )
        )
    target_refs = [
        next(
            value
            for value in result.references
            if value.recommendation_id == target.recommendation_id
        )
        for result in results
    ]
    assert target_refs[0].recommendation_id == target_refs[1].recommendation_id
    assert target_refs[0].revision_id != target_refs[1].revision_id
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendations "
                "WHERE business_id=%s AND company_id=%s AND status='open'",
                (business_id, company_id),
            ).fetchone()[0]
            == 1
        )
        history_count = connection.execute(
            "SELECT count(*) FROM operational.assessment_revisions "
            "WHERE business_id=%s AND recommendation_id=%s",
            (business_id, target.recommendation_id),
        ).fetchone()[0]
        assert history_count == 4

    # Cooldown suppresses reassessment but does not resolve the occurrence. A
    # later selected run may append after its persisted expiry.
    current_time[0] += timedelta(seconds=1)
    with psycopg.connect(url) as connection:
        PostgresSuppressionBlockRepository(PsycopgDatabaseSession(connection)).append(
            SuppressionBlock(
                uuid4(),
                business_id,
                company_id,
                SuppressionKind("cooldown"),
                current_time[0],
                expires_at=current_time[0] + timedelta(days=1),
            )
        )
        connection.commit()
    during_cooldown = service.execute(
        principal, GenerateRecommendationsRequest(strategy_id)
    )
    assert all(
        value.recommendation_id != target.recommendation_id
        for value in during_cooldown.references
    )
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.assessment_revisions WHERE recommendation_id=%s",
                (target.recommendation_id,),
            ).fetchone()[0]
            == 4
        )
    current_time[0] += timedelta(days=2)
    after_cooldown = service.execute(
        principal, GenerateRecommendationsRequest(strategy_id)
    )
    assert any(
        value.recommendation_id == target.recommendation_id
        for value in after_cooldown.references
    )

    # A Later pause is a separate blocker and does not resolve the occurrence.
    current_time[0] += timedelta(seconds=1)
    with psycopg.connect(url) as connection:
        PostgresSuppressionBlockRepository(PsycopgDatabaseSession(connection)).append(
            SuppressionBlock(
                uuid4(),
                business_id,
                company_id,
                SuppressionKind("pause"),
                current_time[0],
                expires_at=current_time[0] + timedelta(days=1),
                created_by_user_id=owner,
                reason="test pause",
            )
        )
        connection.commit()
    paused = service.execute(principal, GenerateRecommendationsRequest(strategy_id))
    assert all(
        value.recommendation_id != target.recommendation_id
        for value in paused.references
    )
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.assessment_revisions WHERE recommendation_id=%s",
                (target.recommendation_id,),
            ).fetchone()[0]
            == 5
        )
    current_time[0] += timedelta(days=2)
    after_pause = service.execute(
        principal, GenerateRecommendationsRequest(strategy_id)
    )
    assert any(
        value.recommendation_id == target.recommendation_id
        for value in after_pause.references
    )

    # An exact retained-source revision may be prepared without exposure, then
    # confirmed once. Replay returns the original handoff and frozen cadence.
    after_pause_target = next(
        value
        for value in after_pause.references
        if value.recommendation_id == target.recommendation_id
    )
    claim_tokens = iter((f"claim-{suffix}-first", f"claim-{suffix}-renewed"))
    prepare_service = RecommendationOfferService(
        lambda: PostgresProspectingUnitOfWork(factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: current_time[0],
        token_factory=lambda: next(claim_tokens),
    )
    confirm_service = RecommendationOfferService(
        lambda: PostgresProspectingUnitOfWork(factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: current_time[0],
    )
    request_key = f"brightroom-offer-{suffix}"
    with psycopg.connect(url) as connection:
        before_prepare = connection.execute(
            "SELECT (SELECT count(*) FROM operational.offer_cycles WHERE business_id=%s),"
            "(SELECT count(*) FROM operational.offer_cycle_events WHERE business_id=%s),"
            "(SELECT count(*) FROM operational.suppression_blocks "
            "WHERE business_id=%s AND kind='cooldown')",
            (business_id, business_id, business_id),
        ).fetchone()
    prepare_request = PrepareRecommendationOfferRequest(
        target.recommendation_id, after_pause_target.revision_id, request_key
    )
    prepared = prepare_service.prepare(principal, prepare_request)
    assert prepared.status.value == "preparing"
    assert prepared.claim_token == f"claim-{suffix}-first"
    assert prepared.presented_at is None
    with psycopg.connect(url) as connection:
        after_prepare = connection.execute(
            "SELECT (SELECT count(*) FROM operational.offer_cycles WHERE business_id=%s),"
            "(SELECT count(*) FROM operational.offer_cycle_events WHERE business_id=%s),"
            "(SELECT count(*) FROM operational.suppression_blocks "
            "WHERE business_id=%s AND kind='cooldown')",
            (business_id, business_id, business_id),
        ).fetchone()
        claim_audit = connection.execute(
            "SELECT payload FROM operational.offer_cycle_events "
            "WHERE offer_cycle_id=%s AND event_kind='preparing_acquired'",
            (prepared.offer_cycle_id,),
        ).fetchone()[0]
    assert after_prepare == tuple(
        value + (1 if index < 2 else 0) for index, value in enumerate(before_prepare)
    )
    assert claim_audit["claim_token_fingerprint"]
    assert f"claim-{suffix}" not in str(claim_audit)
    prepare_replay = prepare_service.prepare(principal, prepare_request)
    assert prepare_replay == prepared

    confirm_request = ConfirmRecommendationOfferRequest(
        prepared.offer_cycle_id, prepared.claim_token
    )
    with pytest.raises(ConflictError):
        confirm_service.confirm(
            principal,
            ConfirmRecommendationOfferRequest(prepared.offer_cycle_id, "wrong-token"),
        )
    with pytest.raises(ConflictError):
        prepare_service.prepare(
            principal,
            PrepareRecommendationOfferRequest(
                target.recommendation_id,
                uuid4(),
                request_key,
            ),
        )
    with pytest.raises(NotFoundError):
        confirm_service.confirm(Principal(uuid4(), uuid4()), confirm_request)

    with psycopg.connect(url) as connection:
        original_company_name = connection.execute(
            "SELECT name FROM gold.company WHERE id=%s", (company_id,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE gold.company SET name=%s WHERE id=%s",
            (f"{original_company_name} changed", company_id),
        )
        connection.commit()
    with pytest.raises(ConflictError):
        confirm_service.confirm(principal, confirm_request)
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT status,claim_token FROM operational.offer_cycles WHERE id=%s",
            (prepared.offer_cycle_id,),
        ).fetchone() == ("preparing", prepared.claim_token)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND company_id=%s AND kind='cooldown'",
                (business_id, company_id),
            ).fetchone()[0]
            == before_prepare[2]
        )
        connection.execute(
            "UPDATE gold.company SET name=%s WHERE id=%s",
            (original_company_name, company_id),
        )
        connection.commit()

    expired_prepared = prepared
    expired_request = prepare_request
    current_time[0] = expired_prepared.lease_expires_at + timedelta(seconds=1)
    renewed_request_key = f"{request_key}-after-expiry"
    renewed_request = PrepareRecommendationOfferRequest(
        target.recommendation_id,
        after_pause_target.revision_id,
        renewed_request_key,
    )
    prepared = prepare_service.prepare(principal, renewed_request)
    assert prepared.status.value == "preparing"
    assert prepared.claim_token == f"claim-{suffix}-renewed"
    confirm_request = ConfirmRecommendationOfferRequest(
        prepared.offer_cycle_id, prepared.claim_token
    )
    expired_replay = prepare_service.prepare(principal, expired_request)
    assert expired_replay.status.value == "abandoned"
    assert expired_replay.claim_token is None
    with pytest.raises(ConflictError):
        confirm_service.confirm(
            principal,
            ConfirmRecommendationOfferRequest(
                expired_prepared.offer_cycle_id,
                expired_prepared.claim_token,
            ),
        )
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT status,claim_token FROM operational.offer_cycles WHERE id=%s",
            (expired_prepared.offer_cycle_id,),
        ).fetchone() == ("abandoned", None)
        assert connection.execute(
            "SELECT status,claim_token FROM operational.offer_cycles WHERE id=%s",
            (prepared.offer_cycle_id,),
        ).fetchone() == ("preparing", prepared.claim_token)

    confirmed_at = current_time[0] + timedelta(seconds=1)
    current_time[0] = confirmed_at
    confirmed = confirm_service.confirm(principal, confirm_request)
    assert confirmed.presented_at == confirmed_at
    assert confirmed.cooldown_expires_at == confirmed_at + timedelta(days=30)
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE operational.business_recommendation_preferences "
            "SET repeat_interval_days=45 WHERE business_id=%s",
            (business_id,),
        )
        updated_preferences = connection.execute(
            "SELECT business_id,repeat_interval_days,updated_at "
            "FROM operational.business_recommendation_preferences WHERE business_id=%s",
            (business_id,),
        ).fetchone()
        connection.commit()
    assert updated_preferences[0:2] == (business_id, 45)
    assert updated_preferences[2] >= preferences_before[2]
    confirm_replay = confirm_service.confirm(principal, confirm_request)
    assert confirm_replay == confirmed
    confirmed_prepare_replay = prepare_service.prepare(principal, renewed_request)
    assert confirmed_prepare_replay.status.value == "confirmed"
    assert confirmed_prepare_replay.claim_token is None
    assert confirmed_prepare_replay.lease_expires_at is None
    with psycopg.connect(url) as connection:
        terminal_claim_token = connection.execute(
            "SELECT claim_token FROM operational.offer_cycles WHERE id=%s",
            (prepared.offer_cycle_id,),
        ).fetchone()[0]
        event_rows = connection.execute(
            "SELECT event_kind,payload FROM operational.offer_cycle_events "
            "WHERE offer_cycle_id=%s ORDER BY recorded_at,id",
            (prepared.offer_cycle_id,),
        ).fetchall()
        cooldown_rows = connection.execute(
            "SELECT created_at,effective_at,expires_at,created_by_user_id "
            "FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s AND kind='cooldown' "
            "ORDER BY created_at,id",
            (business_id, company_id),
        ).fetchall()
    assert terminal_claim_token is None
    assert [row[0] for row in event_rows] == [
        "preparing_acquired",
        "preparing_confirmed",
    ]
    assert event_rows[1][1]["repeat_interval_days"] == 30
    assert (
        event_rows[1][1]["preference_updated_at"] == preferences_before[2].isoformat()
    )
    assert event_rows[1][1]["accepted_at"] == confirmed_at.isoformat()
    assert cooldown_rows[-1] == (
        confirmed_at,
        confirmed_at,
        confirmed_at + timedelta(days=30),
        owner,
    )
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycle_events "
                "WHERE offer_cycle_id=%s",
                (prepared.offer_cycle_id,),
            ).fetchone()[0]
            == 2
        )

    # A known mismatch and then disappeared current evidence leave the last
    # retained assessment readable and never auto-resolve the occurrence.
    current_time[0] += timedelta(days=31)
    current_time[0] += timedelta(minutes=16)
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE gold.company SET country='US' WHERE id=%s", (company_id,)
        )
        connection.commit()
    mismatch_again = service.execute(
        principal, GenerateRecommendationsRequest(strategy_id)
    )
    assert all(
        value.recommendation_id != target.recommendation_id
        for value in mismatch_again.references
    )
    with psycopg.connect(url) as connection:
        latest_revision_id = connection.execute(
            "SELECT current_revision_id FROM operational.recommendations WHERE id=%s",
            (target.recommendation_id,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE gold.company_signal SET company_id=%s "
            "WHERE source='eu_startups' AND source_stable_id=%s",
            (guard_company_id, stable_id),
        )
        connection.commit()
    current_time[0] += timedelta(seconds=1)
    unavailable = service.execute(
        principal, GenerateRecommendationsRequest(strategy_id)
    )
    assert all(
        value.recommendation_id != target.recommendation_id
        for value in unavailable.references
    )
    with PostgresProspectingUnitOfWork(factory, read_only=True) as work:
        retained = work.recommendations.get_owned(business_id, target.recommendation_id)
        assert retained.status.value == "open"
        assert retained.current_revision_id == latest_revision_id
    read_before = None
    with psycopg.connect(url) as connection:
        read_before = connection.execute(
            "SELECT count(*) FROM operational.command_receipts WHERE business_id=%s",
            (business_id,),
        ).fetchone()[0]
    unavailable_view = read_service.get_recommendation(
        principal,
        target.recommendation_id,
        assessment_revision_id=target.revision_id,
    )
    assert unavailable_view.recommendation.current_revision_id == latest_revision_id
    assert unavailable_view.assessment == revision
    assert unavailable_view.assessment.id == target.revision_id
    assert unavailable_view.evidence_state == "unavailable"
    assert unavailable_view.current_eligibility == "unavailable"
    with PostgresProspectingUnitOfWork(factory, read_only=True) as work:
        assert (
            work.assessment_revisions.get_owned(
                business_id, target.recommendation_id, latest_revision_id
            )
            is not None
        )
        assert (
            work.recommendations.get_owned(
                business_id, target.recommendation_id
            ).current_revision_id
            == latest_revision_id
        )
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts WHERE business_id=%s",
                (business_id,),
            ).fetchone()[0]
            == read_before
        )
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND scope='recommendation_generation:on_demand'",
                (business_id,),
            ).fetchone()[0]
            >= 7
        )
        stored_result = connection.execute(
            "SELECT result_snapshot FROM operational.command_receipts "
            "WHERE business_id=%s AND result_snapshot->>'run_id'=%s",
            (business_id, str(generated.run_id)),
        ).fetchone()[0]
        assert stored_result["references"][0]["revision_id"] == str(target.revision_id)
        assert (
            connection.execute(
                "SELECT id,username,status FROM operational.accounts WHERE id=%s",
                (account_id,),
            ).fetchone()
            == account_before
        )
        assert (
            connection.execute(
                "SELECT id,first_name,last_name,email,phone_number,country_of_residence "
                "FROM operational.users WHERE id=%s",
                (owner,),
            ).fetchone()
            == user_before
        )
        assert (
            connection.execute(
                "SELECT business_id,repeat_interval_days,updated_at "
                "FROM operational.business_recommendation_preferences WHERE business_id=%s",
                (business_id,),
            ).fetchone()
            == updated_preferences
        )
        assert (
            connection.execute(
                "SELECT s.id,s.service_offering_id,s.ideal_client_profile_id,o.name,o.description,"
                "i.name,i.geographies FROM operational.client_discovery_strategies s "
                "JOIN operational.service_offerings o ON o.id=s.service_offering_id "
                "JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id "
                "WHERE s.business_id=%s ORDER BY s.id",
                (business_id,),
            ).fetchall()
            == configuration_before
        )
        assert (
            connection.execute(
                "SELECT to_jsonb(profile) FROM operational.professional_profiles profile "
                "WHERE user_id=%s",
                (owner,),
            ).fetchone()[0]
            == personal_profile_before
        )
        assert connection.execute(
            "SELECT name,tagline,website,location,description,capabilities "
            "FROM operational.businesses WHERE id=%s",
            (business_id,),
        ).fetchone() == (None, None, None, None, None, None)
        if connection.execute(
            "SELECT to_regclass('operational.recommendation_batches')"
        ).fetchone()[0]:
            assert (
                connection.execute(
                    "SELECT count(*) FROM operational.recommendation_batches "
                    "WHERE user_id=%s",
                    (owner,),
                ).fetchone()[0]
                == 0
            )

    # Five empty successful runs, a weekly empty run, and a sixth on-demand
    # success prove receipts count runs rather than selected rows or revisions.
    current_time[0] += timedelta(days=1)
    for _ in range(5):
        assert (
            service.execute(
                principal, GenerateRecommendationsRequest(strategy_id)
            ).references
            == ()
        )
    assert service.execute_weekly(business_id).references == ()
    assert (
        service.execute(
            principal, GenerateRecommendationsRequest(strategy_id)
        ).references
        == ()
    )
    with psycopg.connect(url) as connection:
        window_start = current_time[0] - timedelta(minutes=15)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND scope='recommendation_generation:on_demand' "
                "AND recorded_at>%s",
                (business_id, window_start),
            ).fetchone()[0]
            == 6
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND scope='recommendation_generation:weekly' "
                "AND recorded_at>%s",
                (business_id, window_start),
            ).fetchone()[0]
            == 1
        )
    with pytest.raises(RateLimitError) as limited:
        service.execute(principal, GenerateRecommendationsRequest(strategy_id))
    assert limited.value.retry_after_seconds == 900
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.command_receipts "
                "WHERE business_id=%s AND scope='recommendation_generation:on_demand' "
                "AND recorded_at>%s",
                (business_id, current_time[0] - timedelta(minutes=15)),
            ).fetchone()[0]
            == 6
        )


def test_simple_generation_holds_configuration_until_revision_commit(
    retained_management_database_url, monkeypatch
):
    from threading import Event
    from time import monotonic, sleep

    from huginn.management.persistence.repositories.discovery_strategy import (
        PostgresClientDiscoveryStrategyRepository,
    )
    from tests.management.persistence.retained_prospecting_fixtures import (
        generate_retained_brightroom_selection,
    )

    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selection = generate_retained_brightroom_selection(context)
    with psycopg.connect(context.database_url) as connection:
        repository = PostgresClientDiscoveryStrategyRepository(
            PsycopgDatabaseSession(connection)
        )
        first = repository.get_owned(context.business_id, context.strategy_id)
        second = repository.get_owned(context.business_id, context.second_strategy_id)
        repository.set_single_configuration(
            context.business_id,
            first.service_offering_id,
            first.ideal_client_profile_id,
        )
        old_revision = connection.execute(
            "SELECT to_jsonb(r) FROM operational.assessment_revisions r WHERE id=%s",
            (selection.revision_id,),
        ).fetchone()[0]
    profiles_read, proceed = Event(), Event()

    class PausingSource(PostgresRecommendationGenerationSource):
        def active_profiles(self, owner_user_id):
            profiles = super().active_profiles(owner_user_id)
            profiles_read.set()
            assert proceed.wait(10)
            return profiles

    service = RecommendationGenerationService(
        lambda: PostgresProspectingUnitOfWork(context.connection_factory),
        source_factory=PausingSource,
        clock=lambda: context.current_time[0],
        simple_discovery_enabled=True,
    )

    def switch():
        with psycopg.connect(context.database_url) as connection:
            return PostgresClientDiscoveryStrategyRepository(
                PsycopgDatabaseSession(connection)
            ).set_single_configuration(
                context.business_id,
                second.service_offering_id,
                second.ideal_client_profile_id,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        generated = pool.submit(
            service.execute,
            context.principal,
            GenerateRecommendationsRequest(context.strategy_id),
        )
        try:
            assert profiles_read.wait(5)
            switched = pool.submit(switch)
            deadline = monotonic() + 5
            waiting = False
            while monotonic() < deadline and not switched.done():
                with psycopg.connect(context.database_url) as observer:
                    waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND cardinality(pg_blocking_pids(pid))>0 AND query LIKE '%operational.businesses%FOR UPDATE%')"
                    ).fetchone()[0]
                if waiting:
                    break
                sleep(0.01)
            assert waiting, "setup must wait for the generation configuration lock"
            assert not switched.done()
        finally:
            proceed.set()
        assert generated.result(timeout=10).references
        assert switched.result(timeout=10).id == context.second_strategy_id
    with psycopg.connect(context.database_url) as connection:
        assert connection.execute(
            "SELECT id FROM operational.client_discovery_strategies WHERE business_id=%s AND is_active",
            (context.business_id,),
        ).fetchall() == [(context.second_strategy_id,)]
        assert (
            connection.execute(
                "SELECT to_jsonb(r) FROM operational.assessment_revisions r WHERE id=%s",
                (selection.revision_id,),
            ).fetchone()[0]
            == old_revision
        )
