import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.recommendations import (
    PostgresRecommendationRepository,
)
from tests.management.test_matches_query_integration import _user


def test_batches_preserve_snapshot_history_owner_isolation_and_rollback(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        conn.execute(Path("db/schema/operational-recommendations.sql").read_text())
        owner, _ = _user(conn, "recommendations")
        other, _ = _user(conn, "other-recommendations")
        repository = PostgresRecommendationRepository(PsycopgDatabaseSession(conn))
        batch, strategy = uuid4(), uuid4()
        snapshot = {
            "batch": {"items": [{"id": "occurrence"}]},
            "source": {
                "description": "Original consulting context",
                "source_url": "https://example.test/source",
            },
        }
        now = datetime.now(UTC)
        repository.save_batch(owner, batch, strategy, now, json.dumps(snapshot))
        assert json.loads(repository.get_batch(owner, batch)) == snapshot
        assert json.loads(repository.latest_batch(owner, strategy)) == snapshot
        assert repository.get_batch(other, batch) is None
        assert repository.latest_batch(other, strategy) is None
        for choice in ("saved", "dismissed"):
            repository.append_feedback(
                owner, batch, uuid4(), "occurrence", now, json.dumps({"choice": choice})
            )
        assert sorted(
            json.loads(item)["choice"] for item in repository.feedback(owner, batch)
        ) == ["dismissed", "saved"]
        assert repository.feedback(other, batch) == ()
        with pytest.raises(NotFoundError):
            repository.append_feedback(other, batch, uuid4(), "occurrence", now, "{}")
        assert (
            conn.execute(
                "SELECT snapshot FROM operational.recommendation_batches WHERE id=%s",
                (batch,),
            ).fetchone()[0]
            == snapshot
        )
        for query in (
            "UPDATE operational.recommendation_batches SET snapshot='{}' WHERE id=%s",
            "DELETE FROM operational.recommendation_batches WHERE id=%s",
            "DELETE FROM operational.recommendation_feedback WHERE batch_id=%s",
        ):
            with pytest.raises(psycopg.Error), conn.transaction():
                conn.execute(query, (batch,))
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                "INSERT INTO operational.recommendation_feedback(id,user_id,batch_id,recommendation_id,created_at,payload) VALUES (%s,%s,%s,'absent',now(),'{}')",
                (uuid4(), owner, batch),
            )
        assert len(repository.feedback(owner, batch)) == 2
        conn.rollback()
        assert repository.get_batch(owner, batch) is None


def test_profiles_are_active_owned_snapshots(management_database_url):
    with psycopg.connect(management_database_url) as conn:
        owner, _ = _user(conn, "profile")
        other, _ = _user(conn, "profile-other")
        offering = conn.execute(
            "INSERT INTO operational.service_offerings(user_id,name,description) VALUES (%s,'Analytics','Build reporting dashboards') RETURNING id",
            (owner,),
        ).fetchone()[0]
        icp = conn.execute(
            "INSERT INTO operational.ideal_client_profiles(user_id,name) VALUES (%s,'Small startups') RETURNING id",
            (owner,),
        ).fetchone()[0]
        strategy = conn.execute(
            "INSERT INTO operational.client_discovery_strategies(user_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,'Research',%s,%s,true) RETURNING id",
            (owner, offering, icp),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO operational.professional_profiles(user_id,headline) VALUES (%s,'Consultant')",
            (owner,),
        )
        repository = PostgresRecommendationRepository(PsycopgDatabaseSession(conn))
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
        batch = uuid4()
        repository.save_batch(
            owner, batch, strategy, datetime.now(UTC), json.dumps({"profile": snapshot})
        )
        conn.execute(
            "DELETE FROM operational.client_discovery_strategies WHERE id=%s",
            (strategy,),
        )
        assert json.loads(repository.get_batch(owner, batch))["profile"] == snapshot
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
        repository = PostgresRecommendationRepository(PsycopgDatabaseSession(conn))
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


def test_additive_migration_preserves_committed_snapshots_and_feedback():
    from tests.postgres_harness import provisioned_postgres

    with (
        provisioned_postgres("huginn_recommendations_migration") as database_url,
        psycopg.connect(database_url) as conn,
    ):
        migration = Path("db/schema/operational-recommendations.sql").read_text()
        conn.execute(migration)
        owner, _ = _user(conn, "committed-recommendation")
        repository = PostgresRecommendationRepository(PsycopgDatabaseSession(conn))
        batch, strategy = uuid4(), uuid4()
        snapshot = {
            "batch": {"items": [{"id": "original"}]},
            "context": "Original preserved context",
        }
        repository.save_batch(
            owner, batch, strategy, datetime.now(UTC), json.dumps(snapshot)
        )
        repository.append_feedback(
            owner,
            batch,
            uuid4(),
            "original",
            datetime.now(UTC),
            '{"choice":"saved"}',
        )
        conn.commit()
        conn.execute(migration)
        assert json.loads(repository.get_batch(owner, batch)) == snapshot
        assert tuple(
            json.loads(item) for item in repository.feedback(owner, batch)
        ) == ({"choice": "saved"},)


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
        repository = PostgresRecommendationRepository(PsycopgDatabaseSession(conn))
        result = repository.candidates(
            ("data",), now - timedelta(days=1), now + timedelta(days=1), limit=1
        )
        assert [company.company_id for company in result] == [relevant_company]
        assert result[0].observations[0].description == "Data pipeline consulting"
        assert (
            repository.candidates(
                ("d.ta",), now - timedelta(days=1), now + timedelta(days=1), limit=1
            )
            == ()
        )
