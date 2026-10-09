from dataclasses import dataclass


@dataclass(frozen=True)
class ListInvocationsRequest:
    limit: int = 20
    offset: int = 0
    state: str | None = None
