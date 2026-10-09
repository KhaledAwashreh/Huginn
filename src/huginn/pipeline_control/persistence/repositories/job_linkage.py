from uuid import UUID

from huginn.management.persistence.contracts.database import DatabaseSession


class PostgresJobLinkageRepository:
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def set_lineage(
        self,
        job_run_id: UUID,
        invocation_id: UUID | None,
        parent_job_run_id: UUID | None,
        execution_kind: str | None,
    ) -> None:
        self.connection.execute(
            "UPDATE ops.job_runs SET invocation_id = %s, parent_job_run_id = %s, execution_kind = %s WHERE id = %s",
            (invocation_id, parent_job_run_id, execution_kind, job_run_id),
        )
