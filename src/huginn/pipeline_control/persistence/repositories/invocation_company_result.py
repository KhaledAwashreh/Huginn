from uuid import UUID

from huginn.management.persistence.contracts.database import DatabaseSession


class PostgresInvocationCompanyResultRepository:
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def record(
        self, invocation_id: UUID, company_id: UUID, stage_job_run_id: UUID
    ) -> None:
        self.connection.execute(
            "INSERT INTO ops.pipeline_company_results (invocation_id, company_id, stage_job_run_id) "
            "VALUES (%s, %s, %s) ON CONFLICT (invocation_id, company_id) DO NOTHING",
            (invocation_id, company_id, stage_job_run_id),
        )
