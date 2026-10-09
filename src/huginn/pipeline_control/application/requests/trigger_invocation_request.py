from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TriggerInvocationRequest:
    requester_account_id: UUID
    request_id: UUID
