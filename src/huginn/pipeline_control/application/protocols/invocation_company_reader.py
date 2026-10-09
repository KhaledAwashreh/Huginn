from typing import Protocol
from uuid import UUID

from huginn.pipeline_control.application.read_models.invocation_company_result import (
    InvocationCompanyResult,
)


class InvocationCompanyReader(Protocol):
    def read(
        self, invocation_id: UUID, limit: int, offset: int
    ) -> tuple[str, tuple[InvocationCompanyResult, ...], int]: ...
