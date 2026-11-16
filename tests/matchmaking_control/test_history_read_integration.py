"""Legacy run history remains readable after admission and execution retire."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.matchmaking_control.persistence.database.unit_of_work import (
    PostgresMatchmakingControlUnitOfWork,
)
from huginn.matchmaking_control.persistence.queries.run_reader import PostgresRunReader


def test_stored_run_and_target_history_remain_readable(integration_database_url):
    now = datetime(2026, 11, 15, tzinfo=UTC)
    account_id, run_id, request_id, user_id = (uuid4() for _ in range(4))
    with psycopg.connect(integration_database_url) as connection:
        connection.execute(
            "INSERT INTO operational.accounts(id,username,password_hash) "
            "VALUES (%s,%s,'history-fixture')",
            (account_id, f"history-{account_id}"),
        )
        connection.execute(
            "INSERT INTO ops.matchmaking_runs "
            "(id,requester_account_id,request_id,canonical_request,target_kind,cutoff,as_of,state,requested_at,finished_at,target_count,settled_target_count,safe_error_code) "
            "VALUES (%s,%s,%s,%s,'user',%s,%s,'interrupted',%s,%s,1,1,'executor_interrupted')",
            (
                run_id,
                account_id,
                request_id,
                psycopg.types.json.Jsonb({"target": "legacy"}),
                now - timedelta(days=30),
                now,
                now - timedelta(days=1),
                now,
            ),
        )
        connection.execute(
            "INSERT INTO ops.matchmaking_run_users(run_id,user_id,ordinal,state,finished_at,safe_reason) "
            "VALUES (%s,%s,0,'not_executed',%s,NULL)",
            (run_id, user_id, now),
        )
        connection.commit()

    factory = ManagementConnectionFactory(integration_database_url)
    reader = PostgresRunReader(lambda: PostgresMatchmakingControlUnitOfWork(factory))

    page = reader.list_runs(10, 0)
    detail = reader.get_run(run_id)
    results = reader.list_user_results(run_id, 10, 0)

    assert any(item.id == run_id for item in page.items)
    assert detail is not None
    assert detail.state.value == "interrupted"
    assert detail.safe_error_code == "executor_interrupted"
    assert results is not None
    assert len(results.items) == 1
    assert results.items[0].user_id == user_id
    assert results.items[0].state.value == "not_executed"
