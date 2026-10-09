"""Batch attribution without a second connection. Pipeline design section 6."""

from uuid import UUID

from huginn.elt.gold.ports import CompanyRepositoryPort
from huginn.pipeline_control.application.read_models.tracking_context import (
    TrackingContext,
)


class InvocationCompanyResultWriter:
    def __init__(self, repository: CompanyRepositoryPort) -> None:
        self._repository = repository

    def write(self, context: TrackingContext, company_id: UUID) -> None:
        if context.stage_name != "gold.company":
            raise ValueError("invalid_company_tracking_context")
        self._repository.record_company_result(
            context.invocation_id, context.stage_job_run_id, company_id
        )
