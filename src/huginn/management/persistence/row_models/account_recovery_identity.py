"""Strict persisted row shape for an account recovery identity."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AccountRecoveryIdentityRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    account_id: UUID
    verification_required: bool
    pending_email: str | None = Field(repr=False)
    verified_email: str | None = Field(repr=False)
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime
