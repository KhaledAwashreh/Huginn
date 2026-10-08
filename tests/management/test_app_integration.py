from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.application.services.provisioning import (
    IdentityProvisioningService,
)
from huginn.management.config import ManagementConfig
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.account_recovery_identity import (
    PostgresAccountRecoveryIdentityRepository,
)
from huginn.management.persistence.repositories.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.persistence.repositories.user import PostgresUserRepository
from huginn.management.security.tokens import digest_token


def _provision_identity(factory, **values):
    service = IdentityProvisioningService(
        lambda: UnitOfWork(factory),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        users_factory=lambda uow: PostgresUserRepository(uow.connection),
        profiles_factory=lambda uow: PostgresProfessionalProfileRepository(
            uow.connection
        ),
        recovery_identities_factory=lambda uow: (
            PostgresAccountRecoveryIdentityRepository(uow.connection)
        ),
    )
    return service.provision(ProvisionIdentity(**values))


def test_live_health_and_readiness_on_bootstrapped_database(
    management_database_url,
):
    app = create_app(ManagementConfig(management_database_url))
    client = TestClient(app)

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_live_requests_do_not_bootstrap_empty_database(
    empty_management_database_url,
):
    app = create_app(ManagementConfig(empty_management_database_url))
    client = TestClient(app)

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready"}

    with psycopg.connect(empty_management_database_url) as conn:
        schemas = {
            row[0]
            for row in conn.execute(
                "SELECT schema_name FROM information_schema.schemata"
            )
        }

    assert {"ops", "bronze", "silver", "gold", "operational"}.isdisjoint(schemas)


def test_readiness_rejects_deliberately_incomplete_operational_schema(
    empty_management_database_url,
):
    with psycopg.connect(empty_management_database_url) as conn:
        conn.execute("CREATE SCHEMA operational")
        conn.execute("CREATE TABLE operational.accounts (id UUID PRIMARY KEY)")

    app = create_app(ManagementConfig(empty_management_database_url))
    assert TestClient(app).get("/ready").status_code == 503

    with psycopg.connect(empty_management_database_url) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'operational'"
            )
        }
    assert tables == {"accounts"}


def test_app_construction_and_probes_do_not_reset_persisted_account(
    management_database_url,
):
    username = str(uuid4())
    account_id = None

    try:
        with psycopg.connect(management_database_url) as conn:
            original = conn.execute(
                "INSERT INTO operational.accounts (username, password_hash) "
                "VALUES (%s, %s) "
                "RETURNING id, username, password_hash, status, created_at, updated_at",
                (username, "task-4-test-hash-not-a-real-credential"),
            ).fetchone()
            conn.commit()
            account_id = original[0]

        for _ in range(2):
            app = create_app(ManagementConfig(management_database_url))
            client = TestClient(app)
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200

        with psycopg.connect(management_database_url) as conn:
            persisted = conn.execute(
                "SELECT id, username, password_hash, status, created_at, updated_at "
                "FROM operational.accounts WHERE id = %s",
                (account_id,),
            ).fetchone()

        assert persisted == original
    finally:
        if account_id is not None:
            with psycopg.connect(management_database_url) as conn:
                conn.execute(
                    "DELETE FROM operational.accounts WHERE id = %s",
                    (account_id,),
                )
                conn.commit()


def test_live_login_csrf_logout_and_rejected_token_replay(management_database_url):
    factory = ManagementConnectionFactory(management_database_url)
    username = f"http-session-{uuid4()}"
    password = "correct-horse-battery-staple"
    identity = _provision_identity(
        factory,
        username=username,
        first_name="Ada",
        last_name="Lovelace",
        email=f"{username}@example.test",
        phone_number="+12025550123",
        country_of_residence="US",
        timezone="UTC",
        password=password,
    )
    client = create_app(ManagementConfig(management_database_url, environment="test"))
    client = TestClient(client)

    try:
        login = client.post(
            "/api/v1/sessions", json={"username": username, "password": password}
        )
        assert login.status_code == 200
        csrf_token = login.json()["csrf_token"]
        session_token = client.cookies.get("huginn_management_session")
        with psycopg.connect(management_database_url) as connection:
            digests = connection.execute(
                "SELECT token_digest, csrf_digest FROM operational.sessions "
                "WHERE account_id = %s",
                (identity.account_id,),
            ).fetchone()
        assert digests == (
            digest_token(session_token),
            digest_token(csrf_token),
        )

        bad_csrf = client.delete(
            "/api/v1/sessions/current", headers={"X-CSRF-Token": "wrong-csrf"}
        )
        assert bad_csrf.status_code == 403
        assert client.cookies.get("huginn_management_session") == session_token
        logout = client.delete(
            "/api/v1/sessions/current", headers={"X-CSRF-Token": csrf_token}
        )
        assert logout.status_code == 204
        assert client.cookies.get("huginn_management_session") is None

        client.cookies.set("huginn_management_session", session_token)
        replay = client.delete(
            "/api/v1/sessions/current", headers={"X-CSRF-Token": csrf_token}
        )
        assert replay.status_code == 401
    finally:
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DELETE FROM operational.account_recovery_identity WHERE account_id = %s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.sessions WHERE account_id = %s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.professional_profiles WHERE user_id = %s",
                (identity.user_id,),
            )
            connection.execute(
                "DELETE FROM operational.users WHERE id = %s", (identity.user_id,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s",
                (identity.account_id,),
            )
            connection.commit()


def test_live_password_change_revokes_all_account_sessions(management_database_url):
    factory = ManagementConnectionFactory(management_database_url)
    username = f"http-password-{uuid4()}"
    old_password = "correct-horse-battery-staple"
    new_password = "replacement-battery-horse-staple"
    identity = _provision_identity(
        factory,
        username=username,
        first_name="Grace",
        last_name="Hopper",
        email=f"{username}@example.test",
        phone_number="+12025550123",
        country_of_residence="US",
        timezone="UTC",
        password=old_password,
    )
    client = create_app(ManagementConfig(management_database_url, environment="test"))
    client = TestClient(client)

    try:
        first_login = client.post(
            "/api/v1/sessions",
            json={"username": username, "password": old_password},
        )
        first_csrf = first_login.json()["csrf_token"]
        first_token = client.cookies.get("huginn_management_session")
        second_login = client.post(
            "/api/v1/sessions",
            json={"username": username, "password": old_password},
        )
        second_csrf = second_login.json()["csrf_token"]
        assert first_login.status_code == second_login.status_code == 200
        assert client.cookies.get("huginn_management_session") != first_token

        changed = client.patch(
            "/api/v1/me/password",
            json={"current_password": old_password, "new_password": new_password},
            headers={"X-CSRF-Token": second_csrf},
        )
        assert changed.status_code == 204
        assert client.cookies.get("huginn_management_session") is None
        with psycopg.connect(management_database_url) as connection:
            revoked = connection.execute(
                "SELECT revoked_at FROM operational.sessions WHERE account_id = %s",
                (identity.account_id,),
            ).fetchall()
        assert len(revoked) == 2 and all(row[0] is not None for row in revoked)

        client.cookies.set("huginn_management_session", first_token)
        stale = client.delete(
            "/api/v1/sessions/current", headers={"X-CSRF-Token": first_csrf}
        )
        assert stale.status_code == 401
        assert (
            client.post(
                "/api/v1/sessions",
                json={"username": username, "password": old_password},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/sessions",
                json={"username": username, "password": new_password},
            ).status_code
            == 200
        )
    finally:
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DELETE FROM operational.account_recovery_identity WHERE account_id = %s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.sessions WHERE account_id = %s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.professional_profiles WHERE user_id = %s",
                (identity.user_id,),
            )
            connection.execute(
                "DELETE FROM operational.users WHERE id = %s", (identity.user_id,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s",
                (identity.account_id,),
            )
            connection.commit()


def test_live_two_user_management_crud_end_to_end(management_database_url):
    factory = ManagementConnectionFactory(management_database_url)

    def provision(**values):
        return _provision_identity(factory, **values)

    password = "correct-horse-battery-staple"
    identities = [
        provision(
            username=f"e2e-{index}-{uuid4()}",
            first_name="User",
            last_name=str(index),
            email=f"e2e-{index}-{uuid4()}@example.test",
            phone_number=f"+1202555012{index}",
            country_of_residence="US",
            timezone="UTC",
            password=password,
        )
        for index in (1, 2)
    ]
    app = create_app(ManagementConfig(management_database_url, environment="test"))
    clients = [TestClient(app), TestClient(app)]
    csrf_tokens = []
    try:
        with psycopg.connect(management_database_url) as connection:
            usernames = [
                connection.execute(
                    "SELECT username FROM operational.accounts WHERE id=%s",
                    (identity.account_id,),
                ).fetchone()[0]
                for identity in identities
            ]
        for client, username in zip(clients, usernames, strict=True):
            login = client.post(
                "/api/v1/sessions", json={"username": username, "password": password}
            )
            assert login.status_code == 200
            csrf_tokens.append(login.json()["csrf_token"])

        first, second = clients
        csrf = csrf_tokens[0]
        assert (
            first.patch(
                "/api/v1/me",
                json={"first_name": "Updated"},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        assert (
            first.patch(
                "/api/v1/me/professional-profile",
                json={"skills": [{"name": "Python"}]},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        offering = first.post(
            "/api/v1/offerings",
            json={"name": "Consulting", "description": "Architecture audit"},
            headers={"X-CSRF-Token": csrf},
        )
        icp = first.post(
            "/api/v1/ideal-client-profiles",
            json={
                "name": "SaaS Europe",
                "industries": [{"name": "SaaS"}],
                "company_sizes": [{"band": "11-100"}],
                "geographies": [{"kind": "region", "value": "Europe"}],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert offering.status_code == icp.status_code == 201
        strategy_payload = {
            "name": "Primary",
            "service_offering_id": offering.json()["id"],
            "ideal_client_profile_id": icp.json()["id"],
            "is_active": True,
        }
        first_strategy = first.post(
            "/api/v1/discovery-strategies",
            json=strategy_payload,
            headers={"X-CSRF-Token": csrf},
        )
        second_strategy = first.post(
            "/api/v1/discovery-strategies",
            json={**strategy_payload, "name": "Secondary"},
            headers={"X-CSRF-Token": csrf},
        )
        assert first_strategy.status_code == second_strategy.status_code == 201
        assert (
            len(first.get("/api/v1/discovery-strategies?active=true").json()["items"])
            == 2
        )

        cross_path = f"/api/v1/offerings/{offering.json()['id']}"
        assert second.get(cross_path).status_code == 404
        assert (
            second.patch(
                cross_path,
                json={"name": "Stolen"},
                headers={"X-CSRF-Token": csrf_tokens[1]},
            ).status_code
            == 404
        )
        assert (
            first.delete(cross_path, headers={"X-CSRF-Token": csrf}).status_code == 409
        )
        assert (
            first.delete(
                f"/api/v1/ideal-client-profiles/{icp.json()['id']}",
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 409
        )

        session_token = first.cookies.get("huginn_management_session")
        assert (
            first.delete(
                "/api/v1/sessions/current", headers={"X-CSRF-Token": csrf}
            ).status_code
            == 204
        )
        first.cookies.set("huginn_management_session", session_token)
        assert first.get("/api/v1/me").status_code == 401
    finally:
        with psycopg.connect(management_database_url) as connection:
            account_ids = tuple(identity.account_id for identity in identities)
            user_ids = tuple(identity.user_id for identity in identities)
            connection.execute(
                "DELETE FROM operational.client_discovery_strategies WHERE user_id=ANY(%s)",
                (list(user_ids),),
            )
            connection.execute(
                "DELETE FROM operational.ideal_client_profiles WHERE user_id=ANY(%s)",
                (list(user_ids),),
            )
            connection.execute(
                "DELETE FROM operational.service_offerings WHERE user_id=ANY(%s)",
                (list(user_ids),),
            )
            connection.execute(
                "DELETE FROM operational.sessions WHERE account_id=ANY(%s)",
                (list(account_ids),),
            )
            connection.execute(
                "DELETE FROM operational.professional_profiles WHERE user_id=ANY(%s)",
                (list(user_ids),),
            )
            connection.execute(
                "DELETE FROM operational.account_recovery_identity WHERE account_id=ANY(%s)",
                (list(account_ids),),
            )
            connection.execute(
                "DELETE FROM operational.users WHERE id=ANY(%s)", (list(user_ids),)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id=ANY(%s)",
                (list(account_ids),),
            )
            connection.commit()
