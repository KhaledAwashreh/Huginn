from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN
from huginn.pipeline_control.persistence.database.unit_of_work import (
    PostgresPipelineUnitOfWork,
)


def test_claim_row_lock_allows_guard_fk_claim_on_independent_connection(
    integration_database_url: str,
) -> None:
    account_id, invocation_id = uuid4(), uuid4()
    request_id, owner_id, execution_id = uuid4(), uuid4(), uuid4()
    factory = ManagementConnectionFactory(integration_database_url)
    now = datetime.now(UTC)
    with psycopg.connect(integration_database_url) as connection:
        connection.execute(
            "INSERT INTO operational.accounts (id, username, password_hash) VALUES (%s, %s, 'hash')",
            (account_id, f"pipeline-claim-{account_id}"),
        )
        connection.execute(
            "INSERT INTO ops.pipeline_invocations "
            "(id, requester_account_id, request_id, state, requested_at, plan, company_results_tracking_state) "
            "VALUES (%s, %s, %s, 'queued', %s, %s, 'tracked')",
            (
                invocation_id,
                account_id,
                request_id,
                now,
                Jsonb(SUPPORTED_STAGE_PLAN.to_json()),
            ),
        )

    owner = ExecutionOwner(
        owner_id, execution_id, invocation_id, "test-host", 123, "started"
    )
    try:
        with PostgresPipelineUnitOfWork(factory) as claim_uow:
            claimed = claim_uow.invocations.claim_queued(str(owner_id), now)
            assert claimed is not None and claimed.id == invocation_id
            with PostgresPipelineUnitOfWork(factory) as guard_uow:
                guard_uow.connection.execute("SET LOCAL statement_timeout = 2000")
                assert guard_uow.execution_guard.acquire(owner)
                guard_uow.commit()
            assert claim_uow.invocations.mark_running(invocation_id, str(owner_id), now)
            claim_uow.commit()
        with PostgresPipelineUnitOfWork(factory) as cleanup_uow:
            assert cleanup_uow.execution_guard.release(owner_id)
            cleanup_uow.commit()
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "UPDATE ops.pipeline_execution_guard SET owner_id = NULL, execution_id = NULL, "
                "invocation_id = NULL, host = NULL, supervisor_pid = NULL, supervisor_started_at = NULL, "
                "executor_pid = NULL, executor_started_at = NULL, acquired_at = NULL, released_at = NULL, active = FALSE "
                "WHERE singleton = 1 AND owner_id = %s",
                (owner_id,),
            )
            connection.execute(
                "DELETE FROM ops.pipeline_invocations WHERE id = %s", (invocation_id,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account_id,)
            )
