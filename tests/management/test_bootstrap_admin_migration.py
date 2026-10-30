import json
import os
import subprocess
import sys
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


RUNNER = Path("docker/seed-admin.py").resolve()


def founder_environment(url, first, second):
    return {
        **os.environ,
        "HUGINN_MANAGEMENT_DATABASE_URL": url,
        "HUGINN_BOOTSTRAP_ADMIN_USERNAME": first,
        "HUGINN_BOOTSTRAP_ADMIN_EMAIL": f"{first}@example.test",
        "HUGINN_BOOTSTRAP_ADMIN_PASSWORD": "KhaledSeed!123",
        "HUGINN_BOOTSTRAP_SECOND_ADMIN_USERNAME": second,
        "HUGINN_BOOTSTRAP_SECOND_ADMIN_EMAIL": f"{second}@example.test",
        "HUGINN_BOOTSTRAP_SECOND_ADMIN_PASSWORD": "CraigSeed!123",
    }


def run_founders(environment):
    return subprocess.run(
        [sys.executable, str(RUNNER)], env=environment, capture_output=True, text=True
    )


def test_runner_seeds_both_founders_and_preserves_existing_records(
    management_database_url,
):
    suffix = uuid4().hex
    names = (f"Khaled-{suffix}", f"Craig-{suffix}")
    environment = founder_environment(management_database_url, *names)
    result = run_founders(environment)
    assert result.returncode == 0, result.stderr
    with psycopg.connect(management_database_url) as conn:
        rows = conn.execute(
            """SELECT a.id,a.username,a.role,a.password_hash,u.id,u.first_name,u.last_name,
            p.headline,r.verification_required,r.verified_email
            FROM operational.accounts a JOIN operational.users u ON u.account_id=a.id
            JOIN operational.professional_profiles p ON p.user_id=u.id
            JOIN operational.account_recovery_identity r ON r.account_id=a.id
            WHERE a.username=ANY(%s) ORDER BY a.username""",
            (list(names),),
        ).fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row[2] == "admin"
            assert row[5:8] == (row[1], "Founder", "Huginn co-founder")
            assert row[8:] == (False, None)
            password = "KhaledSeed!123" if row[1] == names[0] else "CraigSeed!123"
            assert verify_password(Password(password), row[3])
            assert password not in result.stdout + result.stderr
    app = create_app(ManagementConfig(database_url=management_database_url))
    for name, password in zip(names, ("KhaledSeed!123", "CraigSeed!123"), strict=True):
        with TestClient(app) as client:
            assert (
                client.post(
                    "/api/v1/sessions",
                    json={"username": name.swapcase(), "password": password},
                ).status_code
                == 200
            )
            assert client.get("/api/v1/sessions/current").json()["role"] == "admin"
    with psycopg.connect(management_database_url) as conn:
        changed = hash_password(Password("ChangedFounder!123"))
        conn.execute(
            "UPDATE operational.accounts SET password_hash=%s,status='disabled' WHERE username=%s",
            (changed, names[0]),
        )
        conn.execute(
            "UPDATE operational.professional_profiles SET headline='Edited profile' WHERE user_id=%s",
            (next(row[4] for row in rows if row[1] == names[0]),),
        )
        before = conn.execute(
            "SELECT a.id,a.username,a.password_hash,a.status,u.id,p.headline FROM operational.accounts a JOIN operational.users u ON u.account_id=a.id JOIN operational.professional_profiles p ON p.user_id=u.id WHERE a.username=ANY(%s) ORDER BY a.username",
            (list(names),),
        ).fetchall()
    environment["HUGINN_BOOTSTRAP_ADMIN_USERNAME"] = names[0].lower()
    assert run_founders(environment).returncode == 0
    with psycopg.connect(management_database_url) as conn:
        after = conn.execute(
            "SELECT a.id,a.username,a.password_hash,a.status,u.id,p.headline FROM operational.accounts a JOIN operational.users u ON u.account_id=a.id JOIN operational.professional_profiles p ON p.user_id=u.id WHERE a.username=ANY(%s) ORDER BY a.username",
            (list(names),),
        ).fetchall()
        assert after == before


def test_second_founder_conflict_rolls_back_first_founder(management_database_url):
    first, second = f"first-{uuid4().hex}", f"second-{uuid4().hex}"
    with psycopg.connect(management_database_url) as conn:
        conn.execute(
            "INSERT INTO operational.accounts(username,password_hash) VALUES (%s,'keep-hash')",
            (second,),
        )
    result = run_founders(founder_environment(management_database_url, first, second))
    assert result.returncode == 1
    with psycopg.connect(management_database_url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.accounts WHERE username=%s", (first,)
            ).fetchone()[0]
            == 0
        )
        assert conn.execute(
            "SELECT role,password_hash FROM operational.accounts WHERE username=%s",
            (second,),
        ).fetchone() == ("user", "keep-hash")


@pytest.mark.parametrize("duplicate", ("username", "email"))
def test_runner_rejects_duplicate_founder_identity_before_connecting(duplicate):
    environment = founder_environment(
        "postgresql://invalid.invalid/unused", "Khaled", "Craig"
    )
    if duplicate == "username":
        environment["HUGINN_BOOTSTRAP_SECOND_ADMIN_USERNAME"] = "kHALED"
    else:
        environment["HUGINN_BOOTSTRAP_SECOND_ADMIN_EMAIL"] = "KHALED@example.test"
    result = run_founders(environment)
    assert result.returncode == 1
    assert "ValueError" in result.stderr
    assert "OperationalError" not in result.stderr
