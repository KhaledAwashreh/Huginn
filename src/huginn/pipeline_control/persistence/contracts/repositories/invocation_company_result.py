from typing import Protocol
from uuid import UUID


class InvocationCompanyResultRepository(Protocol):
    def record(
        self, invocation_id: UUID, company_id: UUID, stage_job_run_id: UUID
    ) -> None: ...
