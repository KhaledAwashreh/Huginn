from huginn.management.presentation.api.responses.common import ResponseModel


class MetricResponse(ResponseModel):
    kind: str
    unit: str
    value: int | float | None
