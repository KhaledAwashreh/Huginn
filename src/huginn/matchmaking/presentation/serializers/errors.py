"""Operator-safe error serialization."""

from huginn.matchmaking.presentation.errors.shapes import OperatorError


def serialize_operator_error(error: OperatorError) -> dict[str, object]:
    return {"error": {"code": error.code, "message": error.message}}
