import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg

from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.prospect import (
    PostgresProspectRepository,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)
from huginn.management.persistence.repositories.suppression_block import (
    PostgresSuppressionBlockRepository,
)
from huginn.matchmaking.domain.policies.lexical_research import offering_terms
from tests.management.persistence.prospecting_fixtures import (
    seed_prospecting_owner_company,
    valid_assessment_revision,
    valid_recommendation,
)
from tests.management.test_matches_query_integration import _user


def test_pending_and_unknown_offers_block_selection_without_expiry_and_only_own_preparing_can_be_excluded(
    management_database_url,
):
    from huginn.management.domain.entities.offer_cycle import OfferCycle
    from huginn.management.domain.value_objects.accepted_offer_cadence import (
        AcceptedOfferCadence,
    )
    from huginn.management.domain.value_objects.offer_cycle_status import (
        OfferCycleStatus,
    )
    from huginn.management.persistence.repositories.assessment_revision import (
        PostgresAssessmentRevisionRepository,
    )
    from huginn.management.persistence.repositories.offer_cycle import (
        PostgresOfferCycleRepository,
    )
    from huginn.management.persistence.repositories.recommendation import (
        PostgresRecommendationRepository,
    )

    now = datetime(2026, 11, 14, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        owner = seed_prospecting_owner_company(connection)
        foreign = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        recommendation = PostgresRecommendationRepository(session).create_open(
            valid_recommendation(owner, at=now)
        )
        revision = PostgresAssessmentRevisionRepository(session).append(
            valid_assessment_revision(owner, recommendation, at=now)
        )
        cycles = PostgresOfferCycleRepository(session)
        cycle = OfferCycle(
            uuid4(),
            owner.business_id,
            owner.company_id,
            recommendation.id,
            revision.id,
            "projection-cycle",
            "a" * 64,
            OfferCycleStatus("preparing"),
            now,
            now,
            "claim-token",
            now + timedelta(minutes=5),
        )
        cycles.acquire_preparing(
            cycle,
            now=now,
            lease_expires_at=cycle.lease_expires_at,
            claim_token=cycle.claim_token,
        )
        connection.commit()
        source = PostgresRecommendationGenerationSource(session)

        def state(at=now, excluded=None, business_id=owner.business_id):
            return source.company_states(
                business_id, (owner.company_id,), at, exclude_offer_cycle_id=excluded
            )[0]

        assert state().pending_delivery is True
        assert state(excluded=cycle.id).pending_delivery is False
        assert state(excluded=uuid4()).pending_delivery is True
        assert state(business_id=foreign.business_id).pending_delivery is False
        cycles.mark_sending(
            owner.business_id,
            owner.company_id,
            cycle.id,
            cycle.claim_token,
            now + timedelta(minutes=1),
            AcceptedOfferCadence(30, now, now + timedelta(minutes=1)),
        )
        connection.commit()
        assert state(at=now + timedelta(days=35)).pending_delivery is True
        assert (
            state(at=now + timedelta(days=35), excluded=cycle.id).pending_delivery
            is True
        )
        cycles.settle_sending(
            owner.business_id,
            owner.company_id,
            cycle.id,
            cycle.claim_token,
            "unknown",
            now + timedelta(minutes=2),
        )
        connection.commit()
        after = state(at=now + timedelta(days=35))
        assert after.uncertain_delivery is True
        assert after.pending_delivery is False
        assert (
            state(at=now + timedelta(days=35), excluded=cycle.id).uncertain_delivery
            is True
        )
        assert state(business_id=foreign.business_id).uncertain_delivery is False


def test_company_state_projection_is_scoped_ordered_and_read_only(
    management_database_url,
):
    now = datetime(2026, 11, 14, tzinfo=UTC)
    with psycopg.connect(management_database_url) as connection:
        first = seed_prospecting_owner_company(connection)
        second = seed_prospecting_owner_company(connection)
        session = PsycopgDatabaseSession(connection)
        blocks = PostgresSuppressionBlockRepository(session)
        blocks.append(
            SuppressionBlock(
                id=uuid4(),
                business_id=first.business_id,
                company_id=first.company_id,
                kind=SuppressionKind("cooldown"),
                created_at=now,
                expires_at=now + timedelta(days=3),
            )
        )
        blocks.append(
            SuppressionBlock(
                id=uuid4(),
                business_id=first.business_id,
                company_id=first.company_id,
                kind=SuppressionKind("pause"),
                created_at=now,
                expires_at=None,
                created_by_user_id=first.owner_user_id,
                reason="indefinite pause",
            )
        )
        blocks.append(
            SuppressionBlock(
                id=uuid4(),
                business_id=first.business_id,
                company_id=first.company_id,
                kind=SuppressionKind("rejection"),
                created_at=now,
                created_by_user_id=first.owner_user_id,
                reason="not relevant",
            )
        )
        PostgresProspectRepository(session).create(
            Prospect(
                id=uuid4(),
                business_id=first.business_id,
                company_id=second.company_id,
                stage=ProspectStage("closed"),
                created_at=now,
                updated_at=now,
                last_active_stage=ProspectStage("contacted"),
            )
        )
        connection.commit()

    with psycopg.connect(management_database_url) as connection:
        source = PostgresRecommendationGenerationSource(
            PsycopgDatabaseSession(connection)
        )
        first_state, second_state = source.company_states(
            first.business_id, (first.company_id, second.company_id), now
        )
        other_business_state = source.company_states(
            second.business_id, (first.company_id, second.company_id), now
        )
        assert first_state.cooldown_until == now + timedelta(days=3)
        assert first_state.paused_indefinitely is True
        assert first_state.rejected is True
        assert first_state.has_relationship is False
        assert second_state.has_relationship is True
        assert second_state.rejected is False
        assert other_business_state[0] == type(first_state)()
        assert other_business_state[1] == type(first_state)()


def test_profiles_are_active_owned_snapshots(management_database_url):
    with psycopg.connect(management_database_url) as conn:
        owner, _ = _user(conn, "profile")
        other, _ = _user(conn, "profile-other")
        business = conn.execute(
            "INSERT INTO operational.businesses(owner_user_id) VALUES (%s) RETURNING id",
            (owner,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO operational.business_recommendation_preferences(business_id) VALUES (%s)",
            (business,),
        )
        offering = conn.execute(
            "INSERT INTO operational.service_offerings(business_id,name,description) VALUES (%s,'Analytics','Build reporting dashboards') RETURNING id",
            (business,),
        ).fetchone()[0]
        icp = conn.execute(
            "INSERT INTO operational.ideal_client_profiles(business_id,name) VALUES (%s,'Small startups') RETURNING id",
            (business,),
        ).fetchone()[0]
        strategy = conn.execute(
            "INSERT INTO operational.client_discovery_strategies(business_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,'Research',%s,%s,true) RETURNING id",
            (business, offering, icp),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO operational.professional_profiles(user_id,headline) VALUES (%s,'Consultant')",
            (owner,),
        )
        repository = PostgresRecommendationGenerationSource(
            PsycopgDatabaseSession(conn)
        )
        profile = repository.profile(owner, strategy)
        assert profile.offering_text == "Analytics\nBuild reporting dashboards"
        snapshot = json.loads(profile.snapshot_json)
        assert snapshot["icp"]["industries"] == []
        assert snapshot["professional_profile"]["headline"] == "Consultant"
        assert repository.profile(other, strategy) is None
        conn.execute(
            "UPDATE operational.client_discovery_strategies SET is_active=false WHERE id=%s",
            (strategy,),
        )
        assert repository.profile(owner, strategy) is None
        assert json.loads(profile.snapshot_json) == snapshot
        conn.rollback()


def test_candidates_preserve_all_current_original_context_and_missing_metadata(
    management_database_url,
):
    from datetime import timedelta

    from psycopg.types.json import Jsonb

    from huginn.elt.silver.models.lifecycle_facts import LifecycleFacts
    from huginn.elt.silver.models.source_extraction import SourceExtraction
    from huginn.elt.silver.repositories.source_currentness_repository import (
        PostgresLifecycleRepository,
    )

    now = datetime.now(UTC)
    domain = f"recommendation-{uuid4().hex}.example.test"
    keys = [f"recommendation-{uuid4().hex}" for _ in range(4)]
    with psycopg.connect(management_database_url) as conn:
        company = conn.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Context company') RETURNING id",
            (domain,),
        ).fetchone()[0]
        for key in keys:
            conn.execute(
                "INSERT INTO bronze.api_ingest(source,stable_id,payload,content_hash,run_id) VALUES ('yc',%s,%s,'hash',%s)",
                (
                    key,
                    Jsonb({"website": f"https://{domain}", "isHiring": False}),
                    uuid4(),
                ),
            )
            conn.execute(
                "INSERT INTO silver.resolved_signals(source,source_stable_id,resolved_company_key,company_name_raw,signal_type,key_derivation) VALUES ('yc',%s,%s,'Context company','other','domain_normalized')",
                (key, domain),
            )
            conn.execute(
                "INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at) VALUES (%s,'yc',%s,'other',now())",
                (company, key),
            )
        conn.commit()
    texts = dict(
        zip(
            keys,
            (
                "Original analytics offering context",
                "Undated original directory context",
                "Unmatched companion source context",
                "Future analytics context",
            ),
            strict=True,
        )
    )
    dates = dict(zip(keys, (now, None, now, now + timedelta(days=2)), strict=True))
    lifecycle = PostgresLifecycleRepository(management_database_url)
    for item in lifecycle.read_inputs("yc"):
        if item.stable_id in texts:
            lifecycle.reconcile(
                item,
                LifecycleFacts(
                    listing_state="available",
                    hiring_state="false",
                    identity_state="consistent",
                    reason="test",
                    explicit_domain=domain,
                    occurred_at=dates[item.stable_id],
                    context=SourceExtraction(
                        source="yc",
                        stable_id=item.stable_id,
                        status="captured",
                        source_url=f"https://example.test/{item.stable_id}",
                        normalized_text=texts[item.stable_id],
                        source_fields={},
                    ),
                ),
            )
    with psycopg.connect(management_database_url) as conn:
        repository = PostgresRecommendationGenerationSource(
            PsycopgDatabaseSession(conn)
        )
        assert all(
            item.company_id != company
            for item in repository.candidates(
                ("analytics",), now - timedelta(days=1), now
            )
        )
        candidates = repository.candidates(
            ("analytics",), now - timedelta(days=1), now + timedelta(days=1)
        )
        result = next(item for item in candidates if item.company_id == company)
        assert result.business_sector is result.country is result.company_scale is None
        assert {item.description for item in result.observations} == {
            texts[key] for key in keys[:3]
        }
        assert any(item.occurred_at is None for item in result.observations)
        assert all(
            item.source_url.startswith("https://example.test/")
            for item in result.observations
        )
        conn.execute(
            "UPDATE bronze.api_ingest SET payload=%s WHERE source='yc' AND stable_id=ANY(%s)",
            (Jsonb({"changed": True}), keys),
        )
        assert all(
            item.company_id != company
            for item in repository.candidates(
                ("analytics",), now - timedelta(days=1), now + timedelta(days=1)
            )
        )
        conn.rollback()


def test_whole_word_retrieval_precedes_company_limit(management_database_url):
    from datetime import timedelta

    from psycopg.types.json import Jsonb

    from huginn.elt.silver.models.lifecycle_facts import LifecycleFacts
    from huginn.elt.silver.models.source_extraction import SourceExtraction
    from huginn.elt.silver.repositories.source_currentness_repository import (
        PostgresLifecycleRepository,
    )

    now = datetime.now(UTC)
    irrelevant_company, relevant_company = sorted((uuid4(), uuid4()))
    contexts = {}
    with psycopg.connect(management_database_url) as conn:
        for company, description in (
            (irrelevant_company, "Database metadata tooling"),
            (relevant_company, "Data pipeline consulting"),
        ):
            domain = f"whole-word-{company.hex}.example.test"
            key = f"whole-word-{uuid4().hex}"
            contexts[key] = (domain, description)
            conn.execute(
                "INSERT INTO gold.company(id,domain,name) VALUES (%s,%s,'Whole word test')",
                (company, domain),
            )
            conn.execute(
                "INSERT INTO bronze.api_ingest(source,stable_id,payload,content_hash,run_id) VALUES ('yc',%s,%s,'hash',%s)",
                (
                    key,
                    Jsonb({"website": f"https://{domain}", "isHiring": False}),
                    uuid4(),
                ),
            )
            conn.execute(
                "INSERT INTO silver.resolved_signals(source,source_stable_id,resolved_company_key,company_name_raw,signal_type,key_derivation) VALUES ('yc',%s,%s,'Whole word test','other','domain_normalized')",
                (key, domain),
            )
            conn.execute(
                "INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at) VALUES (%s,'yc',%s,'other',now())",
                (company, key),
            )
        conn.commit()
    lifecycle = PostgresLifecycleRepository(management_database_url)
    for item in lifecycle.read_inputs("yc"):
        if item.stable_id not in contexts:
            continue
        domain, description = contexts[item.stable_id]
        lifecycle.reconcile(
            item,
            LifecycleFacts(
                listing_state="available",
                hiring_state="false",
                identity_state="consistent",
                reason="test",
                explicit_domain=domain,
                occurred_at=now,
                context=SourceExtraction(
                    source="yc",
                    stable_id=item.stable_id,
                    status="captured",
                    source_url=f"https://example.test/{item.stable_id}",
                    normalized_text=description,
                    source_fields={},
                ),
            ),
        )
    with psycopg.connect(management_database_url) as conn:
        repository = PostgresRecommendationGenerationSource(
            PsycopgDatabaseSession(conn)
        )
        terms = offering_terms(" ".join(f"alpha{i}" for i in range(24)) + " data")
        result = repository.candidates(
            terms, now - timedelta(days=1), now + timedelta(days=1), limit=1
        )
        assert [company.company_id for company in result] == [relevant_company]
        assert result[0].observations[0].description == "Data pipeline consulting"
        assert (
            repository.candidates(
                ("d.ta",), now - timedelta(days=1), now + timedelta(days=1), limit=1
            )
            == ()
        )
