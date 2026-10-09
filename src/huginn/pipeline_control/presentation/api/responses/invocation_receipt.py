from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class InvocationReceiptResponse(ResponseModel):
    id: UUID
    status: str
    requested_at: datetime
