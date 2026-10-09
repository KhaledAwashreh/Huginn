from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class InvocationCompanyResult:
    id: UUID
    name: str
    domain: str | None
    business_sector: tuple[str, ...] | str | None
    country: str | None
    company_scale: str | None
    company_status: str | None
    stage_job_run_id: UUID
