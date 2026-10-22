from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.postgres_harness import SCHEMA_DIR

_MIGRATION = SCHEMA_DIR / "silver-source-context.sql"


def _url_for_dbname(database_url: str, dbname: str) -> str:
    info = conninfo_to_dict(database_url)
    info["dbname"] = dbname
    return make_conninfo(**info)


@contextlib.contextmanager
def _scratch_database(database_url: str) -> Iterator[str]:
    name = f"huginn_ctx_mig_{uuid.uuid4().hex[:10]}"
    admin_url = _url_for_dbname(database_url, "postgres")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    try:
        url = _url_for_dbname(database_url, name)
        with psycopg.connect(url) as connection:
            connection.execute((SCHEMA_DIR / "00_extensions.sql").read_text())
            connection.execute("CREATE SCHEMA silver")
        yield url
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as connection,
        ):
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _apply(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(_MIGRATION.read_text())


def test_standalone_context_migration_matches_bootstrap_section() -> None:
    standalone = _MIGRATION.read_text().splitlines()
    assert standalone[2] == "BEGIN;"
    assert standalone[-1] == "COMMIT;"
    migration_body = "\n".join((*standalone[:2], *standalone[3:-1]))

    bootstrap = (SCHEMA_DIR / "silver.sql").read_text()
    section_start = bootstrap.index(
        "-- Additive, idempotent schema for versioned source context."
    )
    assert migration_body == bootstrap[section_start:].rstrip("\n")


def test_silver_bootstrap_remains_inside_caller_transaction(
    integration_database_url: str,
) -> None:
    with _scratch_database(integration_database_url) as url:
        with (
            pytest.raises(RuntimeError, match="force rollback"),
            psycopg.connect(url) as connection,
        ):
            connection.execute((SCHEMA_DIR / "silver.sql").read_text())
            raise RuntimeError("force rollback")

        with psycopg.connect(url) as connection:
            assert connection.execute(
                "SELECT to_regclass('silver.hn_postings'), "
                "to_regclass('silver.source_context_snapshot')"
            ).fetchone() == (None, None)


def _shape(database_url: str, table: str) -> tuple[tuple[str, str], ...]:
    with psycopg.connect(database_url) as connection:
        return tuple(
            connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'silver' AND table_name = %s "
                "ORDER BY ordinal_position",
                (table,),
            ).fetchall()
        )


def test_context_migration_creates_tables_and_is_idempotent(
    integration_database_url: str,
) -> None:
    with _scratch_database(integration_database_url) as url:
        _apply(url)
        first_snapshot_shape = _shape(url, "source_context_snapshot")
        first_run_shape = _shape(url, "source_context_run")
        first_outcome_shape = _shape(url, "source_context_outcome")

        with psycopg.connect(url) as connection:
            connection.execute(
                "CREATE INDEX source_context_snapshot_source_stable_idx "
                "ON silver.source_context_snapshot (source, stable_id)"
            )
        _apply(url)

        assert first_snapshot_shape == _shape(url, "source_context_snapshot")
        assert first_run_shape == _shape(url, "source_context_run")
        assert first_outcome_shape == _shape(url, "source_context_outcome")
        with psycopg.connect(url) as connection:
            indexes = connection.execute(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'silver' AND tablename = 'source_context_outcome' "
                "ORDER BY indexname"
            ).fetchall()
            assert dict(indexes) == {
                "source_context_outcome_run_idx": (
                    "CREATE INDEX source_context_outcome_run_idx ON "
                    "silver.source_context_outcome USING btree (run_id, status)"
                ),
                "source_context_outcome_snapshot_idx": (
                    "CREATE INDEX source_context_outcome_snapshot_idx ON "
                    "silver.source_context_outcome USING btree (snapshot_id)"
                ),
                "source_context_outcome_run_record_uq": (
                    "CREATE UNIQUE INDEX source_context_outcome_run_record_uq ON "
                    "silver.source_context_outcome USING btree (run_id, source, stable_id)"
                ),
                "source_context_outcome_pkey": (
                    "CREATE UNIQUE INDEX source_context_outcome_pkey ON "
                    "silver.source_context_outcome USING btree (id)"
                ),
            }
            snapshot_indexes = connection.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'silver' AND tablename = 'source_context_snapshot'"
            ).fetchall()
            assert (
                "source_context_snapshot_source_stable_idx",
            ) not in snapshot_indexes
            assert connection.execute(
                "INSERT INTO silver.source_context_run "
                "(source, mode, parser_version, input_fingerprint, status) "
                "VALUES ('hn', 'capture', 'test', %s, 'interrupted') RETURNING status",
                ("a" * 64,),
            ).fetchone() == ("interrupted",)
        assert {column for column, _ in first_snapshot_shape} >= {
            "source",
            "stable_id",
            "payload_sha256",
            "parser_version",
            "normalized_text",
            "source_fields",
            "source_times",
            "captured_at",
        }
        assert {column for column, _ in first_run_shape} >= {
            "mode",
            "input_fingerprint",
            "status",
            "total_inputs",
            "captured_count",
            "excluded_count",
            "failed_count",
        }
        assert {column for column, _ in first_outcome_shape} >= {
            "run_id",
            "source",
            "stable_id",
            "status",
            "snapshot_id",
            "observation_metadata",
        }


def test_context_migration_rejects_incompatible_existing_table_atomically(
    integration_database_url: str,
) -> None:
    with _scratch_database(integration_database_url) as url:
        with psycopg.connect(url) as connection:
            connection.execute(
                "CREATE TABLE silver.source_context_snapshot "
                "(id integer PRIMARY KEY, wrong_shape text NOT NULL)"
            )

        with pytest.raises(psycopg.Error):
            _apply(url)

        assert _shape(url, "source_context_snapshot") == (
            ("id", "integer"),
            ("wrong_shape", "text"),
        )
        assert _shape(url, "source_context_run") == ()
        assert _shape(url, "source_context_outcome") == ()


def test_context_migration_rejects_same_named_wrong_unique_key_atomically(
    integration_database_url: str,
) -> None:
    with _scratch_database(integration_database_url) as url:
        _apply(url)
        with psycopg.connect(url) as connection:
            connection.execute(
                "ALTER TABLE silver.source_context_snapshot "
                "DROP CONSTRAINT source_context_snapshot_version_uq"
            )
            connection.execute(
                "ALTER TABLE silver.source_context_snapshot "
                "ADD CONSTRAINT source_context_snapshot_version_uq UNIQUE (source)"
            )

        with pytest.raises(psycopg.Error, match="incompatible key columns"):
            _apply(url)

        with psycopg.connect(url) as connection:
            definition = connection.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'source_context_snapshot_version_uq'"
            ).fetchone()[0]
            assert definition == "UNIQUE (source)"
            assert connection.execute(
                "SELECT to_regclass('silver.source_context_run'), "
                "to_regclass('silver.source_context_outcome')"
            ).fetchone() == (
                "silver.source_context_run",
                "silver.source_context_outcome",
            )


def test_context_migration_rejects_same_named_wrong_check_atomically(
    integration_database_url: str,
) -> None:
    with _scratch_database(integration_database_url) as url:
        _apply(url)
        with psycopg.connect(url) as connection:
            connection.execute(
                "ALTER TABLE silver.source_context_run "
                "DROP CONSTRAINT source_context_run_total_ck"
            )
            connection.execute(
                "ALTER TABLE silver.source_context_run "
                "ADD CONSTRAINT source_context_run_total_ck CHECK (total_inputs >= 1)"
            )

        with pytest.raises(psycopg.Error, match="incompatible check definition"):
            _apply(url)

        with psycopg.connect(url) as connection:
            definition = connection.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'source_context_run_total_ck'"
            ).fetchone()[0]
            assert "total_inputs >= 1" in definition
