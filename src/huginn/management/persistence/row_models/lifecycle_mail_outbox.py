"""Strict persisted row shape for a lifecycle mail delivery intent."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LifecycleMailOutboxRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: UUID
    account_id: UUID
    purpose: Literal["verify_email", "reset_password"]
    proof_id: UUID
    encrypted_payload: bytes | None = Field(repr=False)
    attempt_count: int
    next_attempt_at: datetime
    state: Literal["pending", "claimed", "sent", "failed", "suppressed"]
    failure_code: str | None
    claim_token: UUID | None = Field(repr=False)
    claimed_at: datetime | None
    lease_until: datetime | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None
