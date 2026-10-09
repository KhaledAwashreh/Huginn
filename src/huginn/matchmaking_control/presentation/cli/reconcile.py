"""Explicit recovery refuses live or counterpart-owned executors."""

import argparse
from uuid import UUID

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.matchmaking_control.application.requests.reconcile_execution_request import (
    ReconcileExecutionRequest,
)
from huginn.matchmaking_control.application.requests.reconcile_run_request import (
    ReconcileRunRequest,
)
from huginn.matchmaking_control.application.services.reconcile_execution_service import (
    ReconcileExecutionService,
)
from huginn.matchmaking_control.application.services.reconcile_run_service import (
    ReconcileRunService,
)
from huginn.matchmaking_control.config import MatchmakingControlConfig
from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
    PostgresExecutionGuard,
)
from huginn.pipeline_control.infrastructure.process_supervisor import (
    ProcessExecutorSupervisor,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reconcile an exactly proven stopped matching executor"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", type=UUID)
    group.add_argument("--execution-id", type=UUID)
    parser.add_argument("--executor-stopped", action="store_true", required=True)
    args = parser.parse_args(argv)
    guard = PostgresExecutionGuard(
        ManagementConnectionFactory(
            MatchmakingControlConfig.from_env().database_url, statement_timeout_ms=2000
        ),
        resource_kind="matchmaking",
    )
    try:
        supervisor = ProcessExecutorSupervisor()
        if args.run_id:
            result = ReconcileRunService(guard, supervisor).execute(
                ReconcileRunRequest(args.run_id, args.executor_stopped)
            )
        else:
            result = ReconcileExecutionService(guard, supervisor).execute(
                ReconcileExecutionRequest(args.execution_id, args.executor_stopped)
            )
        print("interrupted" if result.reconciled else "unchanged")
    except Exception:
        parser.exit(
            1,
            "Recovery rejected; verify stopped identity and matching guard ownership.\n",
        )
    finally:
        guard.close()


if __name__ == "__main__":
    main()
