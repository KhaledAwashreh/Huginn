"""Dedicated synchronous worker; no HTTP lifetime owns execution."""

import argparse
import logging
import signal
import threading

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.pipeline_control.application.requests.run_queued_invocation_request import (
    RunQueuedInvocationRequest,
)
from huginn.pipeline_control.application.services.run_queued_invocation_service import (
    RunQueuedInvocationService,
)
from huginn.pipeline_control.config import PipelineControlConfig
from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
    PostgresExecutionGuard,
)
from huginn.pipeline_control.infrastructure.process_supervisor import (
    ProcessExecutorSupervisor,
    new_execution_owner,
)
from huginn.pipeline_control.persistence.database.unit_of_work import (
    PostgresPipelineUnitOfWork,
)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Run committed pipeline invocations")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    config = PipelineControlConfig.from_env()
    factory = ManagementConnectionFactory(
        config.database_url, statement_timeout_ms=2000
    )
    stopped = threading.Event()
    supervisor = ProcessExecutorSupervisor(
        heartbeat_seconds=config.heartbeat_seconds,
        termination_grace_seconds=config.termination_grace_seconds,
        stop_event=stopped,
    )

    def stop(signum, frame):
        stopped.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    service = RunQueuedInvocationService(
        lambda: PostgresPipelineUnitOfWork(factory),
        lambda: PostgresExecutionGuard(factory),
        supervisor,
        new_execution_owner,
    )
    logging.basicConfig(level=logging.INFO)
    while not stopped.is_set():
        try:
            response = service.execute(RunQueuedInvocationRequest("pipeline-worker"))
            logging.getLogger(__name__).info("Worker result: %s", response.status)
        except Exception:
            logging.getLogger(__name__).exception(
                "Worker stopped with execution state preserved"
            )
            raise SystemExit(1) from None
        if args.once:
            return
        stopped.wait(config.poll_seconds)


if __name__ == "__main__":
    main()
