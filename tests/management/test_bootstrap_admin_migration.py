import json
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.security.passwords import (
    Password,
    hash_password,
    verify_password,
)

MIGRATION = Path("db/schema/operational-bootstrap-admin.sql")


def seed(conn, username, password="SeedAdmin!123", email=None):
    conn.execute(
        "SELECT set_config('huginn.bootstrap_admin', %s, true)",
        (
            json.dumps(
                {
                    "username": username,
                    "password_hash": hash_password(Password(password)),
                    "email": email or f"{username}@example.test",
                }
            ),
        ),
    )
    conn.execute(MIGRATION.read_text())


def test_seed_creates_complete_loginable_admin_and_preserves_later_changes(
    management_database_url,
):
    username = f"seed-{uuid4().hex}"
    with psycopg.connect(management_database_url) as conn:
        seed(conn, username)
        account = conn.execute(
            "SELECT id,password_hash,role FROM operational.accounts WHERE username=%s",
            (username,),
        ).fetchone()
        assert account[2] == "admin"
        assert verify_password(Password("SeedAdmin!123"), account[1])
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.users u JOIN operational.professional_profiles p ON p.user_id=u.id JOIN operational.account_recovery_identity r ON r.account_id=u.account_id WHERE u.account_id=%s AND NOT r.verification_required AND r.verified_email IS NULL",
                (account[0],),
            ).fetchone()[0]
            == 1
        )
    with TestClient(
        create_app(ManagementConfig(database_url=management_database_url))
    ) as client:
        assert (
            client.post(
                "/api/v1/sessions",
                json={"username": username, "password": "SeedAdmin!123"},
            ).status_code
            == 200
        )
        assert client.get("/api/v1/sessions/current").json()["role"] == "admin"
    with psycopg.connect(management_database_url) as conn:
        changed = hash_password(Password("Changed!123"))
        conn.execute(
            "UPDATE operational.accounts SET password_hash=%s,status='disabled' WHERE id=%s",
            (changed, account[0]),
        )
        seed(conn, username.upper(), password="Another!123")
        assert conn.execute(
            "SELECT password_hash,status FROM operational.accounts WHERE id=%s",
            (account[0],),
        ).fetchone() == (changed, "disabled")
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.accounts WHERE lower(username)=lower(%s)",
                (username,),
            ).fetchone()[0]
            == 1
        )


def test_seed_refuses_to_promote_an_existing_ordinary_account(management_database_url):
    username = f"ordinary-{uuid4().hex}"
    with psycopg.connect(management_database_url) as conn:
        conn.execute(
            "INSERT INTO operational.accounts(username,password_hash) VALUES (%s,'original-hash')",
            (username,),
        )
        conn.commit()
        with pytest.raises(psycopg.Error), conn.transaction():
            seed(conn, username.upper())
        assert conn.execute(
            "SELECT role,password_hash FROM operational.accounts WHERE username=%s",
            (username,),
        ).fetchone() == ("user", "original-hash")


def test_seed_email_collision_rolls_back_the_entire_identity(management_database_url):
    username = f"collision-{uuid4().hex}"
    email = f"{uuid4().hex}@example.test"
    with psycopg.connect(management_database_url) as conn:
        seed(conn, f"first-{uuid4().hex}", email=email)
        conn.commit()
        with pytest.raises(psycopg.Error), conn.transaction():
            seed(conn, username, email=email)
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.accounts WHERE username=%s",
                (username,),
            ).fetchone()[0]
            == 0
        )


def test_parallel_seed_runs_create_only_one_identity(management_database_url):
    from concurrent.futures import ThreadPoolExecutor

    username = f"parallel-{uuid4().hex}"

    def run():
        with psycopg.connect(management_database_url) as conn:
            seed(conn, username)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run(), range(2)))
    with psycopg.connect(management_database_url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.accounts a JOIN operational.users u ON u.account_id=a.id JOIN operational.professional_profiles p ON p.user_id=u.id WHERE a.username=%s",
                (username,),
            ).fetchone()[0]
            == 1
        )
