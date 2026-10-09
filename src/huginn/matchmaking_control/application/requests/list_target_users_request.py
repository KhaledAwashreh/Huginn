from dataclasses import dataclass


@dataclass(frozen=True)
class ListTargetUsersRequest:
    search: str = ""
    offset: int = 0
    limit: int = 50
