"""Initial enqueue projection for durable lifecycle mail delivery."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

LifecycleMailPurpose = Literal["verify_email", "reset_password"]


@dataclass(frozen=True, slots=True)
class LifecycleMailOutboxRecord:
    id: UUID
    account_id: UUID
    proof_id: UUID
    purpose: LifecycleMailPurpose
    encrypted_payload: bytes = field(repr=False)
    next_attempt_at: datetime
