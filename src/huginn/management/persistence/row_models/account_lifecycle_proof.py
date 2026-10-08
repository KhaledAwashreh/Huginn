"""Strict persisted row shape for a single-use account lifecycle proof."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AccountLifecycleProofRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: UUID
    account_id: UUID
    token_digest: str = Field(repr=False)
    purpose: Literal["verify_email", "reset_password"]
    destination: str = Field(repr=False)
    expires_at: datetime
    consumed_at: datetime | None
    superseded: bool
    created_at: datetime
