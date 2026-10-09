"""Trusted recovery after inspecting stopped host/process identities."""

import argparse
from uuid import UUID

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.pipeline_control.application.requests.reconcile_execution_request import (
    ReconcileExecutionRequest,
)
from huginn.pipeline_control.application.requests.reconcile_invocation_request import (
    ReconcileInvocationRequest,
)
from huginn.pipeline_control.application.services.reconcile_execution_service import (
    ReconcileExecutionService,
)
from huginn.pipeline_control.application.services.reconcile_invocation_service import (
    ReconcileInvocationService,
)
from huginn.pipeline_control.config import PipelineControlConfig
from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
    PostgresExecutionGuard,
)
from huginn.pipeline_control.infrastructure.process_supervisor import (
    ProcessExecutorSupervisor,
)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile a proven stopped pipeline executor"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--invocation-id", type=UUID)
    group.add_argument("--execution-id", type=UUID)
    parser.add_argument("--executor-stopped", action="store_true", required=True)
    args = parser.parse_args(argv)
    guard = PostgresExecutionGuard(
        ManagementConnectionFactory(
            PipelineControlConfig.from_env().database_url, statement_timeout_ms=2000
        )
    )
    try:
        supervisor = ProcessExecutorSupervisor()
        if args.invocation_id:
            response = ReconcileInvocationService(guard, supervisor).execute(
                ReconcileInvocationRequest(args.invocation_id, args.executor_stopped)
            )
        else:
            response = ReconcileExecutionService(guard, supervisor).execute(
                ReconcileExecutionRequest(args.execution_id, args.executor_stopped)
            )
        print(response.status)
    except Exception:
        parser.exit(
            1,
            "Recovery rejected; verify the exact stopped executor identity and guard ownership.\n",
        )
    finally:
        guard.close()


if __name__ == "__main__":
    main()
