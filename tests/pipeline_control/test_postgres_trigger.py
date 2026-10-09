from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from time import monotonic
from uuid import uuid4

import psycopg

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.pipeline_control.application.errors.trigger import TriggerRateLimitError
from huginn.pipeline_control.application.requests.trigger_invocation_request import (
    TriggerInvocationRequest,
)
from huginn.pipeline_control.application.services.trigger_invocation_service import (
    TriggerInvocationService,
)
from huginn.pipeline_control.domain.errors.invocation import (
    ActiveInvocationConflictError,
)
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN
from huginn.pipeline_control.persistence.database.unit_of_work import (
    PostgresPipelineUnitOfWork,
)
from huginn.pipeline_control.persistence.queries.invocation_reader import (
    PostgresInvocationReader,
)


def test_concurrent_triggers_are_atomic_and_do_not_wait_for_shared_execution_lock(
    integration_database_url: str,
) -> None:
    account_id = uuid4()
    request_ids = (uuid4(), uuid4())
    connection_factory = ManagementConnectionFactory(integration_database_url)
    service = TriggerInvocationService(
        lambda: PostgresPipelineUnitOfWork(connection_factory),
        SUPPORTED_STAGE_PLAN,
        clock=lambda: datetime.now(UTC),
    )
    with psycopg.connect(integration_database_url) as connection:
        connection.execute(
            "INSERT INTO operational.accounts (id, username, password_hash) VALUES (%s, %s, 'hash')",
            (account_id, f"pipeline-trigger-{account_id}"),
        )

    invocations: list = []
    try:
        blocker = psycopg.connect(integration_database_url)
        try:
            blocker.execute("SELECT pg_advisory_lock(%s, %s)", (1213548366, 2))
            barrier = Barrier(2)

            def submit(request_id):
                barrier.wait(timeout=5)
                try:
                    return service.execute(
                        TriggerInvocationRequest(account_id, request_id)
                    )
                except ActiveInvocationConflictError as error:
                    return error

            started_at = monotonic()
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(submit, request_ids))
            assert monotonic() - started_at < 2
            accepted = [
                result for result in results if not isinstance(result, Exception)
            ]
            conflicts = [
                result
                for result in results
                if isinstance(result, ActiveInvocationConflictError)
            ]
            invocations.extend(result.id for result in accepted)
            assert len(accepted) == 1
            assert len(conflicts) == 1
            accepted_request_id = request_ids[results.index(accepted[0])]

            repeated = service.execute(
                TriggerInvocationRequest(account_id, accepted_request_id)
            )
            assert repeated.id == accepted[0].id
            assert repeated.created is False
            reader = PostgresInvocationReader(connection_factory)
            events = reader.events(accepted[0].id, 0, 10)
            assert len(events) == 1
            assert (events[0].sequence, events[0].kind) == (1, "invocation_queued")
            detail = reader.get(accepted[0].id)
            assert detail is not None
            assert len(detail.stages) == 9
            assert {stage.state for stage in detail.stages} == {"pending"}
            with psycopg.connect(integration_database_url) as connection:
                assert connection.execute(
                    "SELECT COUNT(*) FROM ops.pipeline_trigger_throttle WHERE requester_account_id = %s",
                    (account_id,),
                ).fetchone() == (2,)

            for _ in range(8):
                try:
                    service.execute(TriggerInvocationRequest(account_id, uuid4()))
                except ActiveInvocationConflictError:
                    pass
                else:
                    raise AssertionError(
                        "a distinct trigger bypassed active invocation admission"
                    )
            try:
                service.execute(TriggerInvocationRequest(account_id, uuid4()))
            except TriggerRateLimitError as error:
                assert error.retry_after_seconds > 0
            else:
                raise AssertionError("the eleventh distinct request was not throttled")
            assert blocker.execute(
                "SELECT pg_advisory_unlock(%s, %s)", (1213548366, 2)
            ).fetchone() == (True,)
        finally:
            blocker.close()
    finally:
        with psycopg.connect(integration_database_url) as connection:
            if invocations:
                connection.execute(
                    "DELETE FROM ops.pipeline_invocation_events WHERE invocation_id = ANY(%s)",
                    (invocations,),
                )
                connection.execute(
                    "DELETE FROM ops.pipeline_invocations WHERE id = ANY(%s)",
                    (invocations,),
                )
            connection.execute(
                "DELETE FROM ops.pipeline_trigger_throttle WHERE requester_account_id = %s",
                (account_id,),
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account_id,)
            )
