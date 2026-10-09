from uuid import UUID

from huginn.management.persistence.contracts.database import ConnectionFactory
from huginn.pipeline_control.application.read_models.invocation_company_result import (
    InvocationCompanyResult,
)


class PostgresInvocationCompanyReader:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def read(
        self, invocation_id: UUID, limit: int, offset: int
    ) -> tuple[str, tuple[InvocationCompanyResult, ...], int]:
        connection = self._connection_factory.connect()
        try:
            row = connection.execute(
                "SELECT company_results_tracking_state FROM ops.pipeline_invocations WHERE id = %s",
                (invocation_id,),
            ).fetchone()
            if row is None:
                return "not_found", (), 0
            tracking_state = row[0]
            if tracking_state != "tracked":
                return "unknown_legacy", (), 0
            total = connection.execute(
                "SELECT COUNT(*) FROM ops.pipeline_company_results WHERE invocation_id = %s",
                (invocation_id,),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT c.id, c.name, c.domain, c.business_sector, c.country, c.company_scale, c.company_status, r.stage_job_run_id "
                "FROM ops.pipeline_company_results AS r JOIN gold.company AS c ON c.id = r.company_id "
                "WHERE r.invocation_id = %s ORDER BY c.id ASC LIMIT %s OFFSET %s",
                (invocation_id, limit, offset),
            ).fetchall()
            items = tuple(
                InvocationCompanyResult(
                    id=r[0],
                    name=r[1],
                    domain=r[2],
                    business_sector=tuple(r[3]) if isinstance(r[3], list) else r[3],
                    country=r[4],
                    company_scale=r[5],
                    company_status=r[6],
                    stage_job_run_id=r[7],
                )
                for r in rows
            )
            return tracking_state, items, total
        finally:
            connection.close()
