"""Fresh-install and additive-upgrade coverage for pipeline-control DDL."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.postgres_harness import BASE_SCHEMA_FILES, SCHEMA_DIR, SCHEMA_FILES


@contextlib.contextmanager
def _empty_database(database_url: str) -> Iterator[str]:
    name = f"huginn_pipeline_control_{uuid.uuid4().hex[:10]}"
    admin_url = make_conninfo(
        **{**conninfo_to_dict(database_url), "dbname": "postgres"}
    )
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    target_url = make_conninfo(**{**conninfo_to_dict(database_url), "dbname": name})
    try:
        yield target_url
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as connection,
        ):
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _apply(connection: psycopg.Connection, files: tuple[str, ...]) -> None:
    for filename in files:
        connection.execute((SCHEMA_DIR / filename).read_text())


def test_empty_database_fresh_bootstrap_applies_full_ordered_schema(
    integration_database_url: str,
) -> None:
    with (
        _empty_database(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as connection,
    ):
        _apply(connection, SCHEMA_FILES)
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'ops' AND table_name LIKE 'pipeline_%'"
        ).fetchall()
        assert {row[0] for row in tables} == {
            "pipeline_invocations",
            "pipeline_invocation_events",
            "pipeline_trigger_throttle",
            "pipeline_execution_guard",
            "pipeline_company_results",
        }
        assert connection.execute(
            "SELECT active FROM ops.pipeline_execution_guard WHERE singleton = 1"
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = 'operational' AND table_name = 'accounts' AND column_name = 'role'"
        ).fetchone() == ("'user'::text",)
        lineage = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'ops' AND table_name = 'job_runs' "
            "AND column_name IN ('invocation_id', 'parent_job_run_id', 'execution_kind')"
        ).fetchall()
        assert {row[0] for row in lineage} == {
            "invocation_id",
            "parent_job_run_id",
            "execution_kind",
        }


def test_legacy_upgrade_keeps_rows_and_fabricates_no_pipeline_attribution(
    integration_database_url: str,
) -> None:
    account_id = uuid.uuid4()
    company_id = uuid.uuid4()
    stage_id = uuid.uuid4()
    source_id = uuid.uuid4()
    with (
        _empty_database(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as connection,
    ):
        _apply(connection, BASE_SCHEMA_FILES)
        connection.execute(
            "INSERT INTO operational.accounts (id, username, password_hash, status) "
            "VALUES (%s, 'legacy-user', 'hash', 'disabled')",
            (account_id,),
        )
        connection.execute(
            "INSERT INTO gold.company (id, domain, name) VALUES (%s, 'legacy.example', 'Legacy')",
            (company_id,),
        )
        connection.execute(
            "INSERT INTO ops.job_runs (id, source, status, rows_written) VALUES "
            "(%s, 'gold.company', 'succeeded', 1), (%s, 'hn', 'failed', 0)",
            (stage_id, source_id),
        )
        _apply(
            connection,
            ("operational-account-role.sql", "ops-pipeline-control.sql"),
        )
        assert connection.execute(
            "SELECT status, role FROM operational.accounts WHERE id = %s", (account_id,)
        ).fetchone() == ("disabled", "user")
        linked_jobs = connection.execute(
            "SELECT id, source, status, rows_written, invocation_id FROM ops.job_runs ORDER BY id"
        ).fetchall()
        assert {row[0] for row in linked_jobs} == {source_id, stage_id}
        assert {(row[1], row[2], row[3], row[4]) for row in linked_jobs} == {
            ("hn", "failed", 0, None),
            ("gold.company", "succeeded", 1, None),
        }
        assert connection.execute(
            "SELECT COUNT(*) FROM ops.pipeline_invocations"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM ops.pipeline_company_results"
        ).fetchone() == (0,)
