"""Explicit obsolete-workflow cleanup never touches retained source or new history."""

import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from huginn.elt.silver.presentation.cli.source_currentness import (
    main as currentness_main,
)
from huginn.elt.silver.repositories.source_currentness_repository import (
    PostgresLifecycleRepository,
)
from huginn.management.persistence.database.client import PostgresReadiness
from tests.management.persistence.retained_prospecting_fixtures import (
    seed_retained_brightroom_context,
)
from tests.postgres_harness import SCHEMA_FILES, provisioned_postgres

CLEANUP = Path("db/schema/operational-obsolete-prospecting-cleanup.sql")
OBSOLETE = (
    "communication_turn",
    "communication_revision",
    "communication_version",
    "communication",
    "activity",
    "match_feedback",
    "match_score",
    "match_source_evidence",
    "match",
    "weekly_digest_deliveries",
    "recommendation_feedback",
    "recommendation_batches",
)


@pytest.fixture
def cutover_database_url():
    with provisioned_postgres(
        "huginn_prospecting_cutover_test", apply_schema=False
    ) as url:
        with psycopg.connect(url, autocommit=True) as connection:
            # Rehearse an actual old target, before the new content layout exists.
            for filename in SCHEMA_FILES:
                if filename == "operational-weekly-digest-content.sql":
                    continue
                connection.execute((Path("db/schema") / filename).read_text())
        yield url


def _retained_snapshot(connection):
    tables = connection.execute(
        "SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN "
        "('bronze','silver','gold','ops','operational') ORDER BY schemaname,tablename"
    ).fetchall()
    return {
        (schema, table): connection.execute(
            sql.SQL(
                "SELECT coalesce(jsonb_agg(to_jsonb(row) ORDER BY to_jsonb(row)::text),'[]'::jsonb) FROM {}.{} row"
            ).format(sql.Identifier(schema), sql.Identifier(table))
        ).fetchone()[0]
        for schema, table in tables
        if schema != "operational" or table not in OBSOLETE
    }


def _seed_legacy_graph(connection, context):
    now = context.current_time[0]
    match_id = connection.execute(
        "INSERT INTO operational.match(user_id,company_id,notes) VALUES (%s,%s,'legacy memo') RETURNING id",
        (context.owner_user_id, context.company_id),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO operational.match_score(match_id,scoring_algorithm,score) VALUES (%s,'legacy',42)",
        (match_id,),
    )
    connection.execute(
        "INSERT INTO operational.match_feedback(match_id,rating) VALUES (%s,'positive')",
        (match_id,),
    )
    connection.execute(
        "INSERT INTO operational.activity(match_id,type,notes) VALUES (%s,'Note','legacy activity')",
        (match_id,),
    )
    communication = connection.execute(
        "INSERT INTO operational.communication(match_id,channel) VALUES (%s,'email') RETURNING id",
        (match_id,),
    ).fetchone()[0]
    version = connection.execute(
        "INSERT INTO operational.communication_version(communication_id,version_number,content) VALUES (%s,1,'legacy draft') RETURNING id",
        (communication,),
    ).fetchone()[0]
    revision = connection.execute(
        "INSERT INTO operational.communication_revision(communication_version_id,agent_type) VALUES (%s,'user') RETURNING id",
        (version,),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO operational.communication_turn(communication_revision_id,role,content) VALUES (%s,'user','legacy turn')",
        (revision,),
    )
    observation = connection.execute(
        "SELECT observation_id FROM gold.current_source_evidence WHERE company_id=%s LIMIT 1",
        (context.company_id,),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO operational.match_source_evidence(match_id,observation_id,cutoff,as_of) VALUES (%s,%s,%s,%s)",
        (match_id, observation, now - timedelta(days=365), now),
    )
    batch = uuid4()
    connection.execute(
        "INSERT INTO operational.recommendation_batches(id,user_id,strategy_id,created_at,snapshot) VALUES (%s,%s,%s,%s,%s)",
        (
            batch,
            context.owner_user_id,
            context.strategy_id,
            now,
            Jsonb({"batch": {"items": [{"id": "legacy-entry"}]}}),
        ),
    )
    connection.execute(
        "INSERT INTO operational.recommendation_feedback(id,user_id,batch_id,recommendation_id,created_at,payload) VALUES (%s,%s,%s,'legacy-entry',%s,%s)",
        (uuid4(), context.owner_user_id, batch, now, Jsonb({"usefulness": "useful"})),
    )
    connection.execute(
        "INSERT INTO operational.weekly_digest_subscriptions(business_id,enabled,updated_at) VALUES (%s,false,%s)",
        (context.business_id, now),
    )
    delivery = uuid4()
    connection.execute(
        "INSERT INTO operational.weekly_digest_deliveries(id,business_id,recipient_user_id,week_start,created_at,settled_at,state,batch_id,recipient,subject,body,company_ids) VALUES (%s,%s,%s,%s,%s,%s,'sent',%s,'legacy@example.test','Legacy digest','Retained legacy fixture',%s)",
        (
            delivery,
            context.business_id,
            context.owner_user_id,
            now.date() - timedelta(days=now.weekday()),
            now,
            now,
            batch,
            Jsonb([str(context.company_id)]),
        ),
    )
    return match_id, delivery


def test_explicit_cleanup_deletes_only_enumerated_legacy_graph_and_empty_retry_is_a_noop(
    cutover_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(cutover_database_url, monkeypatch)
    with psycopg.connect(cutover_database_url) as connection:
        _seed_legacy_graph(connection, context)
        connection.commit()
        before = _retained_snapshot(connection)
        assert any(
            before[("bronze", table)] for schema, table in before if schema == "bronze"
        )
        connection.execute(CLEANUP.read_text())
        after = _retained_snapshot(connection)
        assert after == before
        for table in OBSOLETE:
            assert (
                connection.execute(
                    sql.SQL("SELECT count(*) FROM operational.{}").format(
                        sql.Identifier(table)
                    )
                ).fetchone()[0]
                == 0
            )
        triggers = connection.execute(
            "SELECT tgname,tgenabled FROM pg_trigger WHERE tgname IN ('match_source_evidence_immutable','recommendation_batches_immutable','recommendation_feedback_immutable') ORDER BY tgname"
        ).fetchall()
        assert len(triggers) == 3 and all(enabled == "O" for _, enabled in triggers)
        connection.execute(CLEANUP.read_text())
        assert _retained_snapshot(connection) == before
        connection.execute(
            Path("db/schema/operational-weekly-digest-content.sql").read_text()
        )
        connection.execute(CLEANUP.read_text())
        for key, value in before.items():
            assert _retained_snapshot(connection)[key] == value


def test_cleanup_refuses_replay_after_new_work_and_preserves_all_rows(
    cutover_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(cutover_database_url, monkeypatch)
    with psycopg.connect(cutover_database_url) as connection:
        _seed_legacy_graph(connection, context)
        connection.execute(
            "INSERT INTO operational.recommendations(id,business_id,company_id,status,created_at,updated_at) VALUES (%s,%s,%s,'open',%s,%s)",
            (
                uuid4(),
                context.business_id,
                context.company_id,
                context.current_time[0],
                context.current_time[0],
            ),
        )
        connection.commit()
        before = _retained_snapshot(connection)
        with pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState, match="new workflow history"
        ):
            connection.execute(CLEANUP.read_text())
        connection.rollback()
        assert _retained_snapshot(connection) == before
        assert (
            connection.execute("SELECT count(*) FROM operational.match").fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendation_batches"
            ).fetchone()[0]
            == 1
        )


def test_cleanup_rolls_back_partial_deletes_and_trigger_changes_on_unexpected_foreign_key(
    cutover_database_url, monkeypatch
):
    context = seed_retained_brightroom_context(cutover_database_url, monkeypatch)
    with psycopg.connect(cutover_database_url) as connection:
        match_id, _ = _seed_legacy_graph(connection, context)
        connection.execute(
            "CREATE TABLE operational.cutover_foreign_probe(match_id UUID REFERENCES operational.match(id))"
        )
        connection.execute(
            "INSERT INTO operational.cutover_foreign_probe VALUES (%s)", (match_id,)
        )
        connection.commit()
        before = _retained_snapshot(connection)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(CLEANUP.read_text())
        connection.rollback()
        assert _retained_snapshot(connection) == before
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.communication_turn"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT tgenabled FROM pg_trigger WHERE tgname='match_source_evidence_immutable'"
            ).fetchone()[0]
            == "O"
        )


@pytest.mark.parametrize(
    "guard",
    [
        "sending",
        "unknown",
        "active_executor",
        "queued_run",
        "new_reservation",
        "unexpected_trigger",
    ],
)
def test_cleanup_refuses_unresolved_work_or_an_unexpected_schema_without_partial_changes(
    cutover_database_url, monkeypatch, guard
):
    context = seed_retained_brightroom_context(cutover_database_url, monkeypatch)
    with psycopg.connect(cutover_database_url) as connection:
        _seed_legacy_graph(connection, context)
        if guard in {"sending", "unknown"}:
            connection.execute(
                "UPDATE operational.weekly_digest_deliveries SET state=%s", (guard,)
            )
        elif guard == "active_executor":
            connection.execute(
                "UPDATE ops.pipeline_execution_guard SET active=true,owner_id=%s,execution_id=%s,host='fixture',supervisor_pid=123,supervisor_started_at='fixture',acquired_at=%s",
                (uuid4(), uuid4(), context.current_time[0]),
            )
        elif guard == "queued_run":
            connection.execute(
                "INSERT INTO ops.matchmaking_runs(id,requester_account_id,request_id,canonical_request,target_kind,cutoff,as_of,state,requested_at,target_count) VALUES (%s,%s,%s,'{}','user',%s,%s,'queued',%s,1)",
                (
                    uuid4(),
                    context.account_id,
                    uuid4(),
                    context.current_time[0],
                    context.current_time[0],
                    context.current_time[0],
                ),
            )
        elif guard == "new_reservation":
            connection.commit()
            connection.execute(CLEANUP.read_text())
            connection.execute(
                Path("db/schema/operational-weekly-digest-content.sql").read_text()
            )
            now = context.current_time[0]
            connection.execute(
                "INSERT INTO operational.weekly_digest_deliveries(id,business_id,recipient_user_id,week_start,created_at) VALUES (%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    context.business_id,
                    context.owner_user_id,
                    now.date() - timedelta(days=now.weekday()),
                    now,
                ),
            )
        elif guard == "unexpected_trigger":
            connection.execute(
                "ALTER TABLE operational.recommendation_batches DISABLE TRIGGER recommendation_batches_immutable"
            )
        connection.commit()
        before = _retained_snapshot(connection)
        delivery_before = connection.execute(
            "SELECT to_jsonb(d) FROM operational.weekly_digest_deliveries d ORDER BY id"
        ).fetchall()
        trigger_before = connection.execute(
            "SELECT tgrelid,tgname,tgenabled FROM pg_trigger WHERE NOT tgisinternal ORDER BY tgrelid,tgname"
        ).fetchall()
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(CLEANUP.read_text())
        connection.rollback()
        assert _retained_snapshot(connection) == before
        assert (
            connection.execute(
                "SELECT to_jsonb(d) FROM operational.weekly_digest_deliveries d ORDER BY id"
            ).fetchall()
            == delivery_before
        )
        assert (
            connection.execute(
                "SELECT tgrelid,tgname,tgenabled FROM pg_trigger WHERE NOT tgisinternal ORDER BY tgrelid,tgname"
            ).fetchall()
            == trigger_before
        )


def test_operator_cutover_setup_reconciliation_and_readiness_on_a_retained_copy(
    cutover_database_url, monkeypatch, tmp_path
):
    context = seed_retained_brightroom_context(cutover_database_url, monkeypatch)
    readiness = PostgresReadiness(cutover_database_url)
    assert readiness.is_ready() is False
    with psycopg.connect(cutover_database_url) as connection:
        _seed_legacy_graph(connection, context)
        connection.commit()
        before = _retained_snapshot(connection)
        connection.execute(
            Path("db/schema/operational-business-ownership.sql").read_text()
        )
        assert _retained_snapshot(connection) == before
        connection.execute(CLEANUP.read_text())
        assert _retained_snapshot(connection) == before
        connection.execute(Path("db/schema/operational-prospecting.sql").read_text())
        connection.execute(
            Path("db/schema/operational-weekly-digest-content.sql").read_text()
        )
        after_setup = _retained_snapshot(connection)
        for key, value in before.items():
            assert after_setup[key] == value
    assert readiness.is_ready() is True
    reports = {}
    for command in ("audit", "reconcile"):
        summary = tmp_path / f"eu-startups-{command}.json"
        result = currentness_main(
            [command, "--source", "eu_startups", "--summary", str(summary)],
            repository_factory=lambda: PostgresLifecycleRepository(
                cutover_database_url
            ),
        )
        assert result == 0
        reports[command] = json.loads(summary.read_text())
        assert reports[command]["status"] == "complete"
    with psycopg.connect(cutover_database_url) as connection:
        after_reconcile = _retained_snapshot(connection)
        for key, value in before.items():
            if key[0] != "silver":
                assert after_reconcile[key] == value
        evidence = connection.execute(
            "SELECT observation_id,source_url,occurred_at FROM gold.current_source_evidence "
            "WHERE company_id=%s ORDER BY observation_id",
            (context.company_id,),
        ).fetchall()
        assert evidence
        assert all(
            url == context.listing_url and occurred_at is not None
            for _, url, occurred_at in evidence
        )
        assert (
            connection.execute("SELECT count(*) FROM operational.match").fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendations"
            ).fetchone()[0]
            == 0
        )
    assert readiness.is_ready() is True
