"""One declared Business capability in profile responses."""

from huginn.management.presentation.api.responses.common import NonBlank, ResponseModel


class BusinessCapabilityResponse(ResponseModel):
    name: NonBlank
