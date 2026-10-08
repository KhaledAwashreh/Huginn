"""Strict persisted row shape for a lifecycle throttle counter."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LifecycleThrottleRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    scope: Literal["receipt_username", "receipt_email", "receipt_ip", "proof_ip"]
    key_digest: str = Field(repr=False)
    window_started_at: datetime
    request_count: int
    created_at: datetime
    updated_at: datetime
