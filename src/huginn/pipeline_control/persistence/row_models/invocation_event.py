from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InvocationEventRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: UUID
    invocation_id: UUID
    sequence: int
    occurred_at: datetime
    kind: str
    transition_key: str
    stage_name: str | None
    source_name: str | None
    safe_code: str | None
    safe_message: str | None
    metrics: list[dict[str, Any]]
