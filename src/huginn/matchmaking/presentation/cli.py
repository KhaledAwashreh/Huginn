"""Retired Match creation operator entry point."""

import json
import sys

from huginn.matchmaking.presentation.errors.shapes import OperatorError
from huginn.matchmaking.presentation.serializers.errors import serialize_operator_error


def main(argv: list[str] | None = None) -> int:
    del argv
    payload = serialize_operator_error(
        OperatorError(
            code="matchmaking_retired",
            message="Match creation has been retired",
        )
    )
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 2
