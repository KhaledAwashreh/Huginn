"""Trusted child: evaluation starts only after durable supervisor acknowledgement."""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import UUID

from huginn.pipeline_control.infrastructure.process_supervisor import current_identity


def main(argv=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", type=UUID)
    group.add_argument("--batch-request")
    parser.add_argument("--worker-id", type=UUID)
    parser.add_argument("--result-path")
    args = parser.parse_args(argv)
    if args.run_id and (args.worker_id is None or args.result_path is not None):
        parser.error("managed identity is required")
    if args.batch_request and (args.result_path is None or args.worker_id is not None):
        parser.error("batch output is required")
    print(json.dumps(asdict(current_identity())), flush=True)
    if sys.stdin.readline() != "GO\n":
        raise SystemExit(2)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    logging.basicConfig(level=logging.INFO)
    try:
        if args.run_id:
            from huginn.management.persistence.database.client import (
                ManagementConnectionFactory,
            )
            from huginn.matchmaking.bootstrap import build_service
            from huginn.matchmaking.config import MatchmakingConfig
            from huginn.matchmaking_control.application.requests.execute_run_request import (
                ExecuteRunRequest,
            )
            from huginn.matchmaking_control.application.services.execute_run_service import (
                ExecuteRunService,
            )
            from huginn.matchmaking_control.config import MatchmakingControlConfig
            from huginn.matchmaking_control.infrastructure.service_matchmaking_executor import (
                ServiceMatchmakingExecutor,
            )
            from huginn.matchmaking_control.persistence.database.unit_of_work import (
                PostgresMatchmakingControlUnitOfWork,
            )

            config = MatchmakingControlConfig.from_env()
            factory = ManagementConnectionFactory(
                config.database_url, statement_timeout_ms=2000
            )
            ExecuteRunService(
                lambda: PostgresMatchmakingControlUnitOfWork(factory),
                ServiceMatchmakingExecutor(
                    build_service(MatchmakingConfig(config.database_url))
                ),
            ).execute(ExecuteRunRequest(args.run_id, args.worker_id))
            outcome = 0
        else:
            from huginn.matchmaking.application.requests.batch_matchmaking_request import (
                BatchMatchmakingRequest,
            )
            from huginn.matchmaking.bootstrap import build_batch_service
            from huginn.matchmaking.config import MatchmakingConfig
            from huginn.matchmaking.presentation.serializers.batch_matchmaking_response import (
                serialize_batch_matchmaking_response,
            )

            data = json.loads(args.batch_request)
            request = BatchMatchmakingRequest(
                tuple(UUID(value) for value in data["user_ids"]),
                datetime.fromisoformat(data["cutoff"]),
                datetime.fromisoformat(data["as_of"]) if data["as_of"] else None,
            )
            response = build_batch_service(MatchmakingConfig.from_env()).execute(
                request
            )
            Path(args.result_path).write_text(
                json.dumps(serialize_batch_matchmaking_response(response))
            )
            outcome = 1 if response.failures else 0
    except Exception as exc:
        logging.getLogger(__name__).error(
            "Matching child stopped (%s)", type(exc).__name__
        )
        outcome = 3
    raise SystemExit(outcome)


if __name__ == "__main__":
    main()
