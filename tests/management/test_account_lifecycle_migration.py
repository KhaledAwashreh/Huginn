"""Lifecycle additive upgrade and fresh-install parity on disposable PostgreSQL 16."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from tests.postgres_harness import SCHEMA_DIR, provisioned_postgres

_TABLES = (
    "account_recovery_identity",
    "account_lifecycle_proofs",
    "lifecycle_mail_outbox",
    "lifecycle_throttle",
)
_MIGRATION = SCHEMA_DIR / "operational-account-lifecycle.sql"
_LEGACY = """
CREATE SCHEMA operational;
CREATE TABLE operational.accounts (
    id UUID PRIMARY KEY,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX accounts_username_lower_key
    ON operational.accounts (lower(username));
CREATE TABLE operational.users (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL UNIQUE REFERENCES operational.accounts(id),
    email TEXT NOT NULL
);
"""


def _shape(conn):
    columns = conn.execute(
        "SELECT table_name, column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns WHERE table_schema = 'operational' "
        "AND table_name = ANY(%s) ORDER BY table_name, ordinal_position",
        (list(_TABLES),),
    ).fetchall()
    constraints = conn.execute(
        "SELECT c.relname, pg_get_constraintdef(k.oid) "
        "FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'operational' AND c.relname = ANY(%s) "
        "ORDER BY c.relname, pg_get_constraintdef(k.oid)",
        (list(_TABLES),),
    ).fetchall()
    indexes = conn.execute(
        "SELECT tablename, indexdef FROM pg_indexes "
        "WHERE schemaname = 'operational' AND tablename = ANY(%s) "
        "ORDER BY tablename, indexname",
        (list(_TABLES),),
    ).fetchall()
    return columns, constraints, indexes


def test_lifecycle_migration_preserves_legacy_identity_and_pending_signup():
    with (
        provisioned_postgres("huginn_lifecycle_legacy", apply_schema=False) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(_LEGACY)
        active_id, disabled_id, pending_id = uuid4(), uuid4(), uuid4()
        for account_id, username, status in (
            (active_id, "TrustedOwner", "active"),
            (disabled_id, "DisabledOwner", "disabled"),
        ):
            conn.execute(
                "INSERT INTO operational.accounts "
                "(id, username, password_hash, status) VALUES (%s,%s,%s,%s)",
                (account_id, username, "existing-secret-hash", status),
            )
            conn.execute(
                "INSERT INTO operational.users (id, account_id, email) "
                "VALUES (%s,%s,%s)",
                (uuid4(), account_id, f"{username}@example.com"),
            )
        before = conn.execute(
            "SELECT * FROM operational.accounts ORDER BY username"
        ).fetchall()
        users_before = conn.execute(
            "SELECT * FROM operational.users ORDER BY id"
        ).fetchall()
        conn.execute(_MIGRATION.read_text())
        assert (
            conn.execute(
                "SELECT * FROM operational.accounts ORDER BY username"
            ).fetchall()
            == before
        )
        assert (
            conn.execute("SELECT * FROM operational.users ORDER BY id").fetchall()
            == users_before
        )
        assert (
            conn.execute(
                "SELECT verification_required, pending_email, verified_email, "
                "verified_at FROM operational.account_recovery_identity"
            ).fetchall()
            == [(False, None, None, None)] * 2
        )

        conn.execute(
            "INSERT INTO operational.accounts "
            "(id, username, password_hash, status) VALUES (%s,%s,%s,%s)",
            (pending_id, "PublicPending", "new-secret-hash", "active"),
        )
        # Fresh accounts must be explicit, never silently trusted by a trigger.
        assert (
            conn.execute(
                "SELECT 1 FROM operational.account_recovery_identity "
                "WHERE account_id = %s",
                (pending_id,),
            ).fetchone()
            is None
        )
        conn.execute(
            "INSERT INTO operational.account_recovery_identity "
            "(account_id, verification_required, pending_email) VALUES (%s,true,%s)",
            (pending_id, "public@example.com"),
        )
        identity_before = conn.execute(
            "SELECT * FROM operational.account_recovery_identity ORDER BY account_id"
        ).fetchall()
        conn.execute(_MIGRATION.read_text())
        assert (
            conn.execute(
                "SELECT * FROM operational.account_recovery_identity ORDER BY account_id"
            ).fetchall()
            == identity_before
        )


def test_lifecycle_upgrade_matches_fresh_columns_constraints_and_indexes():
    with (
        provisioned_postgres("huginn_lifecycle_fresh") as fresh_url,
        provisioned_postgres(
            "huginn_lifecycle_upgrade", apply_schema=False
        ) as legacy_url,
        psycopg.connect(fresh_url, autocommit=True) as fresh,
        psycopg.connect(legacy_url, autocommit=True) as legacy,
    ):
        legacy.execute(_LEGACY)
        legacy.execute(_MIGRATION.read_text())
        fresh_shape = _shape(fresh)
        assert {row[0] for row in fresh_shape[0]} == set(_TABLES)
        assert _shape(legacy) == fresh_shape
        fresh.execute(_MIGRATION.read_text())
        assert _shape(fresh) == fresh_shape


def test_lifecycle_storage_enforces_binding_secret_scrubbing_and_claim_budget():
    with (
        provisioned_postgres("huginn_lifecycle_constraints") as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        account_id, other_id, proof_id = uuid4(), uuid4(), uuid4()
        for identity in (account_id, other_id):
            conn.execute(
                "INSERT INTO operational.accounts (id,username,password_hash) "
                "VALUES (%s,%s,'hash')",
                (identity, str(identity)),
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO operational.account_recovery_identity "
                "(account_id,verification_required,verified_email) "
                "VALUES (%s,false,'unproven@example.com')",
                (account_id,),
            )
        conn.execute(
            "INSERT INTO operational.account_lifecycle_proofs "
            "(id,account_id,token_digest,purpose,destination,expires_at) "
            "VALUES (%s,%s,%s,'verify_email','target@example.com',now()+interval '1 day')",
            (proof_id, account_id, "a" * 64),
        )
        insert_mail = (
            "INSERT INTO operational.lifecycle_mail_outbox "
            "(account_id,proof_id,purpose,encrypted_payload,attempt_count) "
            "VALUES (%s,%s,'verify_email',%s,%s) RETURNING id"
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(insert_mail, (other_id, proof_id, b"encrypted", 0))
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(insert_mail, (account_id, proof_id, b"encrypted", 6))
        mail_id = conn.execute(
            insert_mail, (account_id, proof_id, b"encrypted", 0)
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE operational.lifecycle_mail_outbox SET state='claimed' WHERE id=%s",
                (mail_id,),
            )
        conn.execute(
            "UPDATE operational.lifecycle_mail_outbox SET state='claimed', "
            "attempt_count=5, claim_token=%s, claimed_at=now(), "
            "lease_until=now()+interval '120 seconds' WHERE id=%s",
            (uuid4(), mail_id),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE operational.lifecycle_mail_outbox SET attempt_count=6 WHERE id=%s",
                (mail_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE operational.lifecycle_mail_outbox SET state='pending', "
                "claim_token=NULL, claimed_at=NULL, lease_until=NULL WHERE id=%s",
                (mail_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE operational.lifecycle_mail_outbox SET state='sent' WHERE id=%s",
                (mail_id,),
            )
        conn.execute(
            "UPDATE operational.lifecycle_mail_outbox SET state='sent', "
            "encrypted_payload=NULL, sent_at=now(), "
            "claim_token=NULL, claimed_at=NULL, lease_until=NULL WHERE id=%s",
            (mail_id,),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE operational.lifecycle_mail_outbox SET "
                "failure_code='recipient=target@example.com' WHERE id=%s",
                (mail_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO operational.lifecycle_throttle "
                "(scope,key_digest,window_started_at,request_count) "
                "VALUES ('receipt_username','plaintext-user',now(),1)"
            )


def test_duplicate_legacy_email_aborts_without_merging_or_verifying():
    with (
        provisioned_postgres(
            "huginn_email_duplicate_legacy", apply_schema=False
        ) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(_LEGACY)
        for email in ("Owner@example.test", "owner@EXAMPLE.test"):
            account_id = uuid4()
            conn.execute(
                "INSERT INTO operational.accounts (id,username,password_hash,status) VALUES (%s,%s,'hash','active')",
                (account_id, str(account_id)),
            )
            conn.execute(
                "INSERT INTO operational.users (id,account_id,email) VALUES (%s,%s,%s)",
                (uuid4(), account_id, email),
            )
        before = conn.execute("SELECT * FROM operational.users ORDER BY id").fetchall()
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="Resolve case-insensitive contact and recovery email ownership explicitly",
        ):
            conn.execute(_MIGRATION.read_text())
        conn.execute("ROLLBACK")
        assert (
            conn.execute("SELECT * FROM operational.users ORDER BY id").fetchall()
            == before
        )
        assert (
            conn.execute(
                "SELECT to_regclass('operational.account_recovery_identity')"
            ).fetchone()[0]
            is None
        )
