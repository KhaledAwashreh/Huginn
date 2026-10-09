from typing import Protocol
from uuid import UUID


class JobLinkageRepository(Protocol):
    def set_lineage(
        self,
        job_run_id: UUID,
        invocation_id: UUID | None,
        parent_job_run_id: UUID | None,
        execution_kind: str | None,
    ) -> None: ...
