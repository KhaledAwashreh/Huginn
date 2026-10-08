"""Secret-bearing claim passed from persistence to the mail worker."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

LifecycleMailPurpose = Literal["verify_email", "reset_password"]


@dataclass(frozen=True, slots=True)
class MailDeliveryClaim:
    id: UUID
    account_id: UUID
    proof_id: UUID
    purpose: LifecycleMailPurpose
    encrypted_payload: bytes = field(repr=False)
    claim_token: UUID = field(repr=False)
    attempt_count: int
    lease_until: datetime
