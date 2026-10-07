"""Safe error shape exposed by the operator CLI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorError:
    code: str
    message: str
