from huginn.management.presentation.api.requests.common import RequestModel, RequestUUID


class TriggerInvocationRequest(RequestModel):
    request_id: RequestUUID
