from typing import Any

from huginn.management.presentation.api.responses.common import ResponseModel


class ActiveInvocationErrorResponse(ResponseModel):
    error: dict[str, Any]
