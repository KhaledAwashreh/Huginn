from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Requester:
    account_id: UUID
