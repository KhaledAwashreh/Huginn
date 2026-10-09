from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExecutionGuardRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    owner_id: UUID | None
    execution_id: UUID | None
    invocation_id: UUID | None
    host: str | None
    supervisor_pid: int | None
    supervisor_started_at: str | None
    executor_pid: int | None
    executor_started_at: str | None
    acquired_at: datetime | None
    released_at: datetime | None
    active: bool
    resource_kind: str = "pipeline"
    matchmaking_run_id: UUID | None = None
