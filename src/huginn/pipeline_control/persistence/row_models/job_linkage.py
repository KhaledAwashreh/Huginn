from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobLinkageRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    job_run_id: UUID
    invocation_id: UUID | None
    parent_job_run_id: UUID | None
    execution_kind: str | None
