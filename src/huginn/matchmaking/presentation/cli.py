"""JSON operator entry point for explicit matchmaking batches."""

import argparse
import json
import sys
from datetime import datetime
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
from huginn.matchmaking.presentation.serializers.batch_matchmaking_response import (
    serialize_batch_matchmaking_response,
)
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


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        request = _parse_request(args)
        config = MatchmakingConfig.from_env()
        from huginn.matchmaking.bootstrap import build_batch_service

        response = build_batch_service(config).execute(request)
        _emit(serialize_batch_matchmaking_response(response))
        return 1 if response.failures else 0
    except (InputValidationError, ConfigurationError) as exc:
        code = getattr(exc, "code", "invalid_input")
        message = (
            "Invalid command-line input"
            if code == "invalid_input"
            else "Invalid matchmaking configuration"
        )
        _emit(serialize_operator_error(OperatorError(code=code, message=message)))
        return 2
