"""Reusable disposable source-evidence setup for ELT and matching tests."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from huginn.elt.silver.repositories.source_currentness_repository import (
    PostgresLifecycleRepository,
)
from huginn.elt.silver.services.source_currentness import run_reconcile
from huginn.matchmaking.domain.errors.criteria import CriteriaIssue
from huginn.matchmaking.domain.services.icp_evaluator import compile_icp
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from tests.postgres_harness import SCHEMA_DIR, SCHEMA_FILES

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def seed_company(
    connection: psycopg.Connection,
    *,
    event_at: datetime | None,
    industry: str = "SaaS",
    company_id: UUID | None = None,
    hiring: bool = False,
    status: str = "Active",
) -> tuple[UUID, str]:
    company_id = company_id or uuid4()
    domain = f"{company_id.hex}.example.test"
    connection.execute(
        "INSERT INTO gold.company(id,domain,name,country,business_sector,company_scale) "
        "VALUES (%s,%s,'Evidence fixture','Germany',%s,'0-10')",
        (company_id, domain, [industry]),
    )
    return seed_source(
        connection,
        company_id=company_id,
        domain=domain,
        event_at=event_at,
        hiring=hiring,
        status=status,
    )


def seed_source(
    connection: psycopg.Connection,
    *,
    company_id: UUID,
    domain: str,
    event_at: datetime | None,
    hiring: bool,
    status: str = "Active",
    stable_id: str | None = None,
) -> tuple[UUID, str]:
    stable_id = stable_id or f"evidence-{uuid4().hex}"
    payload: dict[str, object] = {
        "id": stable_id,
        "slug": stable_id,
        "name": "Evidence fixture",
        "website": f"https://{domain}",
        "status": status,
        "isHiring": hiring,
        "one_liner": "A captured directory record for integration tests.",
    }
    if event_at is not None:
        payload["launched_at"] = event_at.timestamp()
    connection.execute(
        "INSERT INTO bronze.api_ingest(source,stable_id,payload,content_hash,run_id) "
        "VALUES ('yc',%s,%s,'evidence-seed',%s)",
        (stable_id, psycopg.types.json.Jsonb(payload), uuid4()),
    )
    connection.execute(
        "INSERT INTO silver.resolved_signals "
        "(source,source_stable_id,resolved_company_key,company_name_raw,signal_type,key_derivation) "
        "VALUES ('yc',%s,%s,'Evidence fixture','other','domain_normalized')",
        (stable_id, domain),
    )
    connection.execute(
        "INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at) "
        "VALUES (%s,'yc',%s,'other',%s)",
        (company_id, stable_id, event_at or NOW),
    )
    return company_id, stable_id


def reconcile(database_url: str) -> None:
    report = run_reconcile("yc", PostgresLifecycleRepository(database_url))
    assert report["status"] == "complete", report


@contextlib.contextmanager
def scratch_database(database_url: str) -> Iterator[str]:
    """Create one owned database initialized with the harness schema."""
    name = f"huginn_evidence_{uuid4().hex[:12]}"
    admin = conninfo_to_dict(database_url)
    admin["dbname"] = "postgres"
    admin_url = make_conninfo(**admin)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    scratch = conninfo_to_dict(database_url)
    scratch["dbname"] = name
    scratch_url = make_conninfo(**scratch)
    try:
        with psycopg.connect(scratch_url, autocommit=True) as connection:
            for filename in SCHEMA_FILES:
                connection.execute((SCHEMA_DIR / filename).read_text())
        yield scratch_url
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as connection,
        ):
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )


def criteria(industry: str = "SaaS") -> CompiledCriteria:
    result = compile_icp(
        industries=({"name": industry},),
        company_sizes=({"band": "0-10"},),
        geographies=({"kind": "country", "value": "Germany"},),
        exclusions=(),
    )
    assert not isinstance(result, CriteriaIssue)
    return result
