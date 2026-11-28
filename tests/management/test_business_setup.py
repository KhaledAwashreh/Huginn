from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime
from threading import Barrier, Event
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.common import Principal
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.security.tokens import digest_token

CSRF = "setup-csrf-token"
PAYLOAD = {
    "business_name": "Fluke Design B.V.",
    "your_name": "Craig Phillips",
    "service_description": "Product design for engineering led startups.",
    "ideal_client_profile": {
        "name": "Engineering led startups in Europe",
        "industries": [{"name": "Software"}],
        "company_sizes": [{"band": "11-100"}],
        "geographies": [{"kind": "country", "value": "Netherlands"}],
        "exclusions": [],
    },
}


def _owner(url):
    with psycopg.connect(url) as conn:
        account = conn.execute(
            "INSERT INTO operational.accounts(username,password_hash) VALUES (%s,'hash') RETURNING id",
            (str(uuid4()),),
        ).fetchone()[0]
        user = conn.execute(
            "INSERT INTO operational.users(account_id,first_name,last_name,email,phone_number,country_of_residence,timezone) VALUES (%s,'Original','Owner',%s,'+12025550123','US','UTC') RETURNING id",
            (account, f"{uuid4()}@example.test"),
        ).fetchone()[0]
        business = conn.execute(
            "INSERT INTO operational.businesses(owner_user_id,tagline,website) VALUES (%s,'Keep tagline','https://example.test') RETURNING id",
            (user,),
        ).fetchone()[0]
    return Principal(account, user), business


def _client(url, principal):
    app = create_app(ManagementConfig(url, environment="test"))
    now = datetime.now(UTC)
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token(CSRF), now, now, None
    )
    authenticated = AuthenticatedSession(principal, session, "opaque")
    app.dependency_overrides[get_authenticated_session] = lambda: authenticated
    client = TestClient(app)
    client.cookies.set("huginn_management_session", "opaque")
    return client


def _save(client, payload=PAYLOAD):
    return client.put(
        "/api/v1/me/business/setup", json=payload, headers={"X-CSRF-Token": CSRF}
    )


def test_setup_save_creates_pair_and_edits_same_records_with_persisted_readback(
    management_database_url,
):
    url = management_database_url
    principal, business_id = _owner(url)
    with _client(url, principal) as client:
        initial = client.get("/api/v1/me/business/setup")
        assert initial.status_code == 200
        assert initial.json()["service_offering"] is None
        assert initial.json()["ideal_client_profile"] is None
        assert initial.headers["cache-control"] == "no-store"
        saved = _save(client)
        assert saved.status_code == 200, saved.text
        first = saved.json()
        changed = {
            **PAYLOAD,
            "business_name": "Craig Phillips Design",
            "service_description": "Research and product design for startups.",
        }
        updated = _save(client, changed)
        assert updated.status_code == 200, updated.text
        second = updated.json()
        assert first["service_offering"]["id"] == second["service_offering"]["id"]
        assert (
            first["ideal_client_profile"]["id"] == second["ideal_client_profile"]["id"]
        )
        assert _save(client, changed).status_code == 200
        assert client.get("/api/v1/me/business/setup").json() == second
    with psycopg.connect(url) as conn:
        assert conn.execute(
            "SELECT name,tagline,website FROM operational.businesses WHERE id=%s",
            (business_id,),
        ).fetchone() == (
            "Craig Phillips Design",
            "Keep tagline",
            "https://example.test",
        )
        assert conn.execute(
            "SELECT first_name,last_name,email,phone_number,country_of_residence,timezone FROM operational.users WHERE id=%s",
            (principal.user_id,),
        ).fetchone() == (
            "Craig",
            "Phillips",
            initial.json()["user"]["email"],
            "+12025550123",
            "US",
            "UTC",
        )
        assert conn.execute(
            "SELECT count(*),min(description) FROM operational.service_offerings WHERE business_id=%s",
            (business_id,),
        ).fetchone() == (1, changed["service_description"])
        assert conn.execute(
            "SELECT count(*) FROM operational.ideal_client_profiles WHERE business_id=%s",
            (business_id,),
        ).fetchone() == (1,)
        assert conn.execute(
            "SELECT service_offering_id,ideal_client_profile_id,is_active FROM operational.client_discovery_strategies WHERE business_id=%s",
            (business_id,),
        ).fetchall() == [
            (
                UUID(first["service_offering"]["id"]),
                UUID(first["ideal_client_profile"]["id"]),
                True,
            )
        ]


def test_setup_requires_csrf_owned_body_and_complete_valid_inputs(
    management_database_url,
):
    principal, _ = _owner(management_database_url)
    with _client(management_database_url, principal) as client:
        assert client.put("/api/v1/me/business/setup", json=PAYLOAD).status_code == 403
        for payload in (
            {**PAYLOAD, "business_id": str(uuid4())},
            {**PAYLOAD, "service_description": " "},
            {**PAYLOAD, "your_name": "Craig"},
            {**PAYLOAD, "ideal_client_profile": None},
        ):
            assert _save(client, payload).status_code == 422
        conflict = {
            **PAYLOAD["ideal_client_profile"],
            "exclusions": [{"kind": "industry", "name": "Software"}],
        }
        assert (
            _save(client, {**PAYLOAD, "ideal_client_profile": conflict}).status_code
            == 422
        )


def test_concurrent_first_setup_saves_create_one_pair(management_database_url):
    url = management_database_url
    principal, business = _owner(url)
    barrier = Barrier(2)

    def save(_):
        with _client(url, principal) as client:
            barrier.wait(timeout=5)
            response = _save(client)
            assert response.status_code == 200, response.text
            return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(save, range(2)))
    assert (
        responses[0]["service_offering"]["id"] == responses[1]["service_offering"]["id"]
    )
    assert (
        responses[0]["ideal_client_profile"]["id"]
        == responses[1]["ideal_client_profile"]["id"]
    )
    with psycopg.connect(url) as conn:
        assert conn.execute(
            "SELECT count(*) FROM operational.client_discovery_strategies WHERE business_id=%s",
            (business,),
        ).fetchone() == (1,)


def test_setup_rolls_back_all_writes_when_pairing_fails(
    management_database_url, monkeypatch
):
    from huginn.management.persistence.repositories.discovery_strategy import (
        PostgresClientDiscoveryStrategyRepository,
    )

    url = management_database_url
    principal, business = _owner(url)

    def fail(*args):
        raise RuntimeError("pairing unavailable")

    monkeypatch.setattr(
        PostgresClientDiscoveryStrategyRepository, "set_single_configuration", fail
    )
    with _client(url, principal) as client:
        before = client.get("/api/v1/me/business/setup").json()
        failed = _save(client)
        assert failed.status_code == 500
        assert client.get("/api/v1/me/business/setup").json() == before
    with psycopg.connect(url) as conn:
        for table in (
            "service_offerings",
            "ideal_client_profiles",
            "client_discovery_strategies",
        ):
            assert conn.execute(
                f"SELECT count(*) FROM operational.{table} WHERE business_id=%s",
                (business,),
            ).fetchone() == (0,)


def test_setup_rejects_unverified_email_changes_and_preserves_delivery(
    management_database_url,
):
    from huginn.management.persistence.database.client import PsycopgDatabaseSession
    from huginn.management.persistence.repositories.digest_subscription_access import (
        PostgresDigestSubscriptionAccess,
    )

    url = management_database_url
    principal, business = _owner(url)
    with psycopg.connect(url) as conn:
        conn.execute(
            "INSERT INTO operational.account_recovery_identity(account_id,verification_required,verified_email,verified_at) VALUES (%s,false,%s,now())",
            (principal.account_id, "verified-owner@example.test"),
        )
        conn.execute(
            "INSERT INTO operational.weekly_digest_subscriptions(business_id,enabled,updated_at) VALUES (%s,true,now())",
            (business,),
        )
    with _client(url, principal) as client:
        before = client.get("/api/v1/me/business/setup").json()
        rejected = _save(client, {**PAYLOAD, "email": "unverified-edit@example.test"})
        assert rejected.status_code == 409, rejected.text
        assert client.get("/api/v1/me/business/setup").json() == before
        saved = _save(client, {**PAYLOAD, "email": before["user"]["email"]})
        assert saved.status_code == 200, saved.text
        assert saved.json()["user"]["email"] == before["user"]["email"]
    with psycopg.connect(url) as conn:
        access = PostgresDigestSubscriptionAccess(PsycopgDatabaseSession(conn))
        assert (
            access.get_for_business(business).recipient == "verified-owner@example.test"
        )
        assert conn.execute(
            "SELECT verified_email,pending_email FROM operational.account_recovery_identity WHERE account_id=%s",
            (principal.account_id,),
        ).fetchone() == ("verified-owner@example.test", None)
        conn.execute(
            "UPDATE operational.account_recovery_identity SET verified_email=NULL,verified_at=NULL WHERE account_id=%s",
            (principal.account_id,),
        )
        assert access.get_for_business(business) is None


def test_setup_edits_existing_service_topics_without_rewriting_captured_history(
    retained_management_database_url, monkeypatch
):
    from huginn.management.application.policies.recommendation_profile_validation import (
        validated_profile_inputs,
    )
    from huginn.management.persistence.database.client import PsycopgDatabaseSession
    from huginn.management.persistence.repositories.recommendation_generation import (
        PostgresRecommendationGenerationSource,
    )
    from tests.management.persistence.retained_prospecting_fixtures import (
        generate_retained_brightroom_selection,
        seed_retained_brightroom_context,
    )

    url = retained_management_database_url
    context = seed_retained_brightroom_context(url, monkeypatch)
    selection = generate_retained_brightroom_selection(context)
    delivery_id = uuid4()
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE operational.client_discovery_strategies SET is_active=false WHERE id=%s",
            (context.second_strategy_id,),
        )
        conn.execute(
            "UPDATE operational.users SET phone_number='+12025550123' WHERE id=%s",
            (context.owner_user_id,),
        )
        conn.execute(
            "INSERT INTO operational.weekly_digest_deliveries(id,business_id,recipient_user_id,week_start,created_at) VALUES (%s,%s,%s,'2026-11-23',now())",
            (delivery_id, context.business_id, context.owner_user_id),
        )
        revision_before = conn.execute(
            "SELECT to_jsonb(r) FROM operational.assessment_revisions r WHERE id=%s",
            (selection.revision_id,),
        ).fetchone()[0]
        delivery_before = conn.execute(
            "SELECT to_jsonb(d) FROM operational.weekly_digest_deliveries d WHERE id=%s",
            (delivery_id,),
        ).fetchone()[0]
        unrelated_before = conn.execute(
            "SELECT to_jsonb(p) FROM operational.professional_profiles p WHERE user_id=%s",
            (context.owner_user_id,),
        ).fetchone()[0]
        other_offering_before = conn.execute(
            "SELECT to_jsonb(o) FROM operational.service_offerings o JOIN operational.client_discovery_strategies s ON s.service_offering_id=o.id WHERE s.id=%s",
            (context.second_strategy_id,),
        ).fetchone()[0]
    with _client(url, context.principal) as client:
        initial = client.get("/api/v1/me/business/setup").json()
        payload = {
            "business_name": "Brightroom consulting",
            "your_name": f"{initial['user']['first_name']} {initial['user']['last_name']}",
            "email": initial["user"]["email"],
            "service_description": "Software engineering and cloud infrastructure",
            "ideal_client_profile": {
                key: initial["ideal_client_profile"][key]
                for key in (
                    "name",
                    "industries",
                    "company_sizes",
                    "geographies",
                    "exclusions",
                )
            },
        }
        saved = _save(client, payload)
        assert saved.status_code == 200, saved.text
        assert saved.json()["service_offering"]["name"] == "Services"
        assert (
            saved.json()["service_offering"]["id"] == initial["service_offering"]["id"]
        )
        assert (
            saved.json()["ideal_client_profile"]["id"]
            == initial["ideal_client_profile"]["id"]
        )
        assert _save(client, payload).json() == saved.json()
    with psycopg.connect(url) as conn:
        profile = PostgresRecommendationGenerationSource(
            PsycopgDatabaseSession(conn)
        ).profile(context.owner_user_id, context.strategy_id)
        _, _, service_terms, _ = validated_profile_inputs(profile)
        assert "software" in service_terms
        assert "coaching" not in service_terms
        assert (
            conn.execute(
                "SELECT to_jsonb(r) FROM operational.assessment_revisions r WHERE id=%s",
                (selection.revision_id,),
            ).fetchone()[0]
            == revision_before
        )
        assert (
            conn.execute(
                "SELECT to_jsonb(d) FROM operational.weekly_digest_deliveries d WHERE id=%s",
                (delivery_id,),
            ).fetchone()[0]
            == delivery_before
        )
        assert (
            conn.execute(
                "SELECT to_jsonb(p) FROM operational.professional_profiles p WHERE user_id=%s",
                (context.owner_user_id,),
            ).fetchone()[0]
            == unrelated_before
        )
        assert (
            conn.execute(
                "SELECT to_jsonb(o) FROM operational.service_offerings o JOIN operational.client_discovery_strategies s ON s.service_offering_id=o.id WHERE s.id=%s",
                (context.second_strategy_id,),
            ).fetchone()[0]
            == other_offering_before
        )


def test_setup_get_holds_shared_configuration_lock_until_all_fields_are_read(
    management_database_url, monkeypatch
):
    from huginn.management.persistence.repositories.business import (
        PostgresBusinessRepository,
    )
    from huginn.management.persistence.repositories.user import PostgresUserRepository

    url = management_database_url
    principal, _ = _owner(url)
    before_payload = PAYLOAD
    with _client(url, principal) as client:
        before_response = _save(client, before_payload)
        assert before_response.status_code == 200
        before = before_response.json()
    reader_paused, release_reader, writer_started = Event(), Event(), Event()
    original_get_user = PostgresUserRepository.get_by_id
    original_lock = PostgresBusinessRepository.get_by_id_for_update

    def pause_after_business_read(repository, user_id):
        if user_id == principal.user_id and not reader_paused.is_set():
            reader_paused.set()
            assert release_reader.wait(timeout=10)
        return original_get_user(repository, user_id)

    def observe_writer_lock(repository, business_id):
        writer_started.set()
        return original_lock(repository, business_id)

    monkeypatch.setattr(PostgresUserRepository, "get_by_id", pause_after_business_read)
    monkeypatch.setattr(
        PostgresBusinessRepository, "get_by_id_for_update", observe_writer_lock
    )
    after_payload = {
        **before_payload,
        "business_name": "Updated business",
        "your_name": "Updated Owner",
        "service_description": "Software and cloud engineering",
        "ideal_client_profile": {
            **PAYLOAD["ideal_client_profile"],
            "name": "Updated ICP",
        },
    }

    def read():
        with _client(url, principal) as client:
            response = client.get("/api/v1/me/business/setup")
            assert response.status_code == 200
            return response.json()

    def write():
        with _client(url, principal) as client:
            response = _save(client, after_payload)
            assert response.status_code == 200, response.text
            return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(read)
        try:
            assert reader_paused.wait(timeout=5)
            writing = pool.submit(write)
            assert writer_started.wait(timeout=5)
            with pytest.raises(TimeoutError):
                writing.result(timeout=0.2)
        finally:
            release_reader.set()
        assert reading.result(timeout=5) == before
        updated = writing.result(timeout=5)
    assert updated["business"]["name"] == "Updated business"
    assert updated["user"]["first_name"] == "Updated"
    assert (
        updated["service_offering"]["description"] == "Software and cloud engineering"
    )
    assert updated["ideal_client_profile"]["name"] == "Updated ICP"
    with _client(url, principal) as client:
        assert client.get("/api/v1/me/business/setup").json() == updated


def test_setup_ambiguous_saved_settings_rejects_without_selecting_or_mutating(
    management_database_url,
):
    principal, business_id = _owner(management_database_url)
    with psycopg.connect(management_database_url) as conn:
        for name in ("First", "Second"):
            conn.execute(
                "INSERT INTO operational.service_offerings(business_id,name,description) VALUES (%s,%s,'Consulting')",
                (business_id, name),
            )
    with _client(management_database_url, principal) as client:
        response = client.get("/api/v1/me/business/setup")
        assert response.status_code == 409
    with psycopg.connect(management_database_url) as conn:
        assert conn.execute(
            "SELECT name FROM operational.service_offerings WHERE business_id=%s ORDER BY name",
            (business_id,),
        ).fetchall() == [("First",), ("Second",)]
