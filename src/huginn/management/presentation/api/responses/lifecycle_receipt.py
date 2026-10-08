"""LifecycleReceiptResponse HTTP projection."""

from huginn.management.presentation.api.responses.common import ResponseModel


class LifecycleReceiptResponse(ResponseModel):
    message: str
