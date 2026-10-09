from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InvocationRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: UUID
    requester_account_id: UUID
    request_id: UUID
    state: Literal["queued", "running", "succeeded", "failed", "interrupted"]
    requested_at: datetime
    plan: list[dict[str, Any]]
    started_at: datetime | None
    finished_at: datetime | None
    worker_id: str | None
    heartbeat_at: datetime | None
    safe_error_code: str | None
    company_results_tracking_state: Literal["tracked", "unknown_legacy"]
