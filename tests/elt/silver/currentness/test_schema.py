"""Additive lifecycle schema contract; see docs/source-currentness.md."""

from uuid import uuid4

import psycopg
import pytest

from tests.postgres_harness import BASE_SCHEMA_FILES, SCHEMA_DIR, provisioned_postgres

MIGRATION = SCHEMA_DIR / "silver-source-currentness.sql"


def test_schema_has_one_canonical_migration():
    assert MIGRATION.is_file()
    from tests.postgres_harness import SCHEMA_FILES

    assert SCHEMA_FILES.count(MIGRATION.name) == 1
    assert SCHEMA_FILES.index(MIGRATION.name) >= len(BASE_SCHEMA_FILES)


def test_migration_is_additive_idempotent_and_preserves_history():
    with (
        provisioned_postgres("lifecycle_upgrade", apply_schema=False) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        for name in BASE_SCHEMA_FILES:
            conn.execute((SCHEMA_DIR / name).read_text())
        company_id = conn.execute(
            "INSERT INTO gold.company (domain, name) VALUES (%s, %s) RETURNING id",
            (f"schema-{uuid4()}.example", "Existing company"),
        ).fetchone()[0]
        conn.execute(MIGRATION.read_text())
        conn.execute(MIGRATION.read_text())
        assert conn.execute(
            "SELECT name FROM gold.company WHERE id = %s", (company_id,)
        ).fetchone() == ("Existing company",)
        observation = conn.execute(
            """INSERT INTO silver.source_lifecycle_observation
               (source, stable_id, raw_token, resolution_token, policy_version,
                context_version, listing_state, hiring_state, identity_state,
                reason, bronze_fetched_at, bronze_last_checked_at)
               VALUES ('yc', 'one', repeat('a',32), repeat('b',32), 'v1',
                       'v1', 'withdrawn', 'false', 'missing', 'inactive', now(), now())
               RETURNING id"""
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO silver.source_currentness
               (source, stable_id, current_observation_id) VALUES ('yc','one',%s)""",
            (observation,),
        )
        for operation in ("UPDATE", "DELETE"):
            statement = (
                "UPDATE silver.source_lifecycle_observation SET reason = 'changed'"
                if operation == "UPDATE"
                else "DELETE FROM silver.source_lifecycle_observation"
            )
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                conn.execute(statement)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                """INSERT INTO silver.source_currentness
                   (source,stable_id,current_observation_id) VALUES ('yc','two',%s)""",
                (observation,),
            )
        conn.execute(MIGRATION.read_text())
        assert (
            conn.execute(
                "SELECT count(*) FROM silver.source_lifecycle_observation"
            ).fetchone()[0]
            == 1
        )


def test_migration_rejects_incompatible_existing_table():
    with (
        provisioned_postgres("lifecycle_incompatible", apply_schema=False) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        for name in BASE_SCHEMA_FILES:
            conn.execute((SCHEMA_DIR / name).read_text())
        conn.execute("CREATE TABLE silver.source_currentness (source text)")
        with pytest.raises(psycopg.errors.RaiseException, match="incompatible"):
            conn.execute(MIGRATION.read_text())
        conn.execute("ROLLBACK")
        assert (
            conn.execute(
                "SELECT to_regclass('silver.source_lifecycle_observation')"
            ).fetchone()[0]
            is None
        )
