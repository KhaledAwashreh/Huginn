from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InvocationCompanyResultRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    invocation_id: UUID
    company_id: UUID
    stage_job_run_id: UUID
