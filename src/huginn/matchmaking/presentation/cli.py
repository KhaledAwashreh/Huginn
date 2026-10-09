"""JSON operator entry point for explicit matchmaking batches."""

import argparse
import json
import sys
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import UUID

from huginn.matchmaking.application.errors.execution import (
    ConfigurationError,
    InputValidationError,
)
from huginn.matchmaking.application.requests.batch_matchmaking_request import (
    BatchMatchmakingRequest,
)
from huginn.matchmaking.config import MatchmakingConfig
from huginn.matchmaking.presentation.errors.shapes import OperatorError
from huginn.matchmaking.presentation.serializers.errors import serialize_operator_error


class JsonArgumentParser(argparse.ArgumentParser):
    """Argparse parser that returns a safe machine-readable failure."""

    def error(self, message: str) -> None:
        del message
        raise InputValidationError("Invalid command-line arguments")


def _parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        prog="python -m huginn.matchmaking",
        description="Create missing Matches for explicitly selected Users.",
    )
    parser.add_argument(
        "--user-id",
        action="append",
        required=True,
        metavar="UUID",
        help="User UUID to evaluate; repeat for a batch",
    )
    parser.add_argument(
        "--cutoff",
        required=True,
        metavar="ISO-8601",
        help="Inclusive signal-window start with an explicit timezone offset",
    )
    parser.add_argument(
        "--as-of",
        metavar="ISO-8601",
        help="Inclusive signal-window end with an explicit timezone offset (default: current time)",
    )
    return parser


def _parse_datetime(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputValidationError(f"Invalid {name} timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InputValidationError(f"{name} timestamp must include a timezone offset")
    return parsed


def _parse_request(args: argparse.Namespace) -> BatchMatchmakingRequest:
    try:
        user_ids = tuple(UUID(value) for value in args.user_id)
    except (ValueError, AttributeError) as exc:
        raise InputValidationError("User IDs must be valid UUIDs") from exc
    cutoff = _parse_datetime(args.cutoff, "cutoff")
    as_of = None if args.as_of is None else _parse_datetime(args.as_of, "as-of")
    if as_of is not None and cutoff > as_of:
        raise InputValidationError("Cutoff must not be later than as-of")
    try:
        return BatchMatchmakingRequest(user_ids=user_ids, cutoff=cutoff, as_of=as_of)
    except (TypeError, ValueError) as exc:
        raise InputValidationError("Invalid matchmaking request") from exc


def _emit(payload: dict[str, object]) -> None:
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


def _execute_guarded(
    config: MatchmakingConfig, request: BatchMatchmakingRequest
) -> tuple[dict[str, object], int]:
    from huginn.management.persistence.database.client import (
        ManagementConnectionFactory,
    )
    from huginn.pipeline_control.application.errors.execution import (
        ExecutionUnavailableError,
    )
    from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
        PostgresExecutionGuard,
    )
    from huginn.pipeline_control.infrastructure.process_supervisor import (
        ProcessExecutorSupervisor,
        new_execution_owner,
    )

    owner = replace(new_execution_owner(None), resource_kind="matchmaking")
    guard = PostgresExecutionGuard(
        ManagementConnectionFactory(config.database_url, statement_timeout_ms=2000),
        resource_kind="matchmaking",
    )
    try:
        if not guard.acquire(owner):
            raise ExecutionUnavailableError("execution_busy")
        with tempfile.TemporaryDirectory(prefix="huginn-matchmaking-") as directory:
            output = Path(directory) / "result.json"
            payload = json.dumps(
                {
                    "user_ids": [str(value) for value in request.user_ids],
                    "cutoff": request.cutoff.isoformat(),
                    "as_of": request.as_of.isoformat() if request.as_of else None,
                }
            )
            command = (
                sys.executable,
                "-m",
                "huginn.matchmaking_control.presentation.cli.executor",
                "--batch-request",
                payload,
                "--result-path",
                str(output),
            )
            supervisor = ProcessExecutorSupervisor(command=command)
            status = supervisor.run(owner, guard)
            if not guard.settle(owner, "succeeded" if status == 0 else "failed"):
                raise ExecutionUnavailableError("execution_unavailable")
            if not output.is_file():
                raise ExecutionUnavailableError("execution_unavailable")
            return json.loads(output.read_text()), status
    finally:
        guard.close()


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        request = _parse_request(args)
        from huginn.matchmaking.application.services.matchmaking_service import (
            resolve_window,
        )
        from huginn.matchmaking.bootstrap import SystemClock

        window = resolve_window(request.cutoff, request.as_of, SystemClock())
        request = replace(request, cutoff=window.cutoff, as_of=window.as_of)
        config = MatchmakingConfig.from_env()
        payload, status = _execute_guarded(config, request)
        _emit(payload)
        return status
    except (InputValidationError, ConfigurationError) as exc:
        code = getattr(exc, "code", "invalid_input")
        message = (
            "Invalid command-line input"
            if code == "invalid_input"
            else "Invalid matchmaking configuration"
        )
        _emit(serialize_operator_error(OperatorError(code=code, message=message)))
        return 2
    except Exception as exc:
        from huginn.pipeline_control.application.errors.execution import (
            ExecutionUnavailableError,
        )

        code = (
            "execution_busy"
            if isinstance(exc, ExecutionUnavailableError)
            and str(exc) == "execution_busy"
            else "execution_unavailable"
        )
        _emit(
            serialize_operator_error(
                OperatorError(
                    code=code,
                    message="Shared execution is busy"
                    if code == "execution_busy"
                    else "Shared execution is unavailable",
                )
            )
        )
        return 1
