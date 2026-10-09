"""Dedicated managed worker sharing collection's exact execution boundary."""

import argparse
import logging
import signal
import sys
import threading
from dataclasses import replace
from datetime import UTC, datetime

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.matchmaking_control.application.responses.execute_run_response import (
    ExecuteRunResponse,
)
from huginn.matchmaking_control.config import MatchmakingControlConfig
from huginn.matchmaking_control.persistence.database.unit_of_work import (
    PostgresMatchmakingControlUnitOfWork,
)
from huginn.pipeline_control.application.errors.execution import (
    ExecutionUnavailableError,
    ExecutorTerminationUnprovenError,
)
from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
    PostgresExecutionGuard,
)
from huginn.pipeline_control.infrastructure.process_supervisor import (
    ProcessExecutorSupervisor,
    new_execution_owner,
)

logger = logging.getLogger(__name__)


def run_once(uow_factory, guard_factory, supervisor_factory):
    guard = guard_factory()
    owner = replace(new_execution_owner(None), resource_kind="matchmaking")
    try:
        with uow_factory() as uow:
            run = uow.runs.claim_next_run(owner.owner_id, datetime.now(UTC))
            if run is None:
                return ExecuteRunResponse(None, "idle")
            owner = replace(owner, matchmaking_run_id=run.id)
            if not guard.acquire(owner):
                return ExecuteRunResponse(run.id, "waiting")
            if not uow.runs.start_run(run.id, owner.owner_id, datetime.now(UTC)):
                raise ExecutionUnavailableError("run_claim_unavailable")
            uow.commit()
        try:
            outcome = supervisor_factory(owner).run(owner, guard)
        except ExecutorTerminationUnprovenError:
            raise
        except BaseException:
            # Supervision raises only after proving child stop, except the
            # distinct unproven-stop error above. Recover journals atomically.
            if not guard.settle(owner, "interrupted", "execution_interrupted"):
                raise ExecutionUnavailableError("settlement_unavailable") from None
            return ExecuteRunResponse(run.id, "interrupted")
        state = "succeeded" if outcome == 0 else "interrupted"
        if not guard.settle(
            owner, state, None if outcome == 0 else "result_tracking_uncertain"
        ):
            raise ExecutionUnavailableError("settlement_unavailable")
        with uow_factory() as uow:
            recorded = uow.runs.get_run_snapshot(run.id)
        return ExecuteRunResponse(run.id, recorded.state.value)
    finally:
        guard.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Execute queued fixed-target matching runs"
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    config = MatchmakingControlConfig.from_env()
    factory = ManagementConnectionFactory(
        config.database_url, statement_timeout_ms=2000
    )
    stopped = threading.Event()

    def stop(signum, frame):
        stopped.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)

    def supervise(owner):
        return ProcessExecutorSupervisor(
            command=(
                sys.executable,
                "-m",
                "huginn.matchmaking_control.presentation.cli.executor",
                "--run-id",
                str(owner.matchmaking_run_id),
                "--worker-id",
                str(owner.owner_id),
            ),
            heartbeat_seconds=config.heartbeat_seconds,
            termination_grace_seconds=config.termination_grace_seconds,
            stop_event=stopped,
        )

    logging.basicConfig(level=logging.INFO)
    while not stopped.is_set():
        try:
            result = run_once(
                lambda: PostgresMatchmakingControlUnitOfWork(factory),
                lambda: PostgresExecutionGuard(factory, resource_kind="matchmaking"),
                supervise,
            )
            logger.info("Matching worker result: %s", result.status)
        except Exception as exc:
            logger.error(
                "Matching worker stopped with durable state preserved (%s)",
                type(exc).__name__,
            )
            raise SystemExit(1) from None
        if args.once:
            return
        stopped.wait(config.poll_seconds)


if __name__ == "__main__":
    main()
