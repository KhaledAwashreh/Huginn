from uuid import uuid4

import psycopg

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig


def test_live_health_and_readiness_on_bootstrapped_database(
    management_database_url,
):
    app = create_app(ManagementConfig(management_database_url))
    client = app.test_client()

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.data == b'{"status":"ok"}\n'
    assert ready.status_code == 200
    assert ready.data == b'{"status":"ready"}\n'


def test_live_requests_do_not_bootstrap_empty_database(
    empty_management_database_url,
):
    app = create_app(ManagementConfig(empty_management_database_url))
    client = app.test_client()

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.data == b'{"status":"ok"}\n'
    assert ready.status_code == 503
    assert ready.data == b'{"status":"not_ready"}\n'

    with psycopg.connect(empty_management_database_url) as conn:
        schemas = {
            row[0]
            for row in conn.execute(
                "SELECT schema_name FROM information_schema.schemata"
            )
        }

    assert {"ops", "bronze", "silver", "gold", "operational"}.isdisjoint(schemas)


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
            client = app.test_client()
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
