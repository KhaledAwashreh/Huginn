from huginn.pipeline_control.application.errors.invocation import (
    InvocationNotFoundError,
)
from huginn.pipeline_control.application.protocols.invocation_reader import (
    InvocationReader,
)
from huginn.pipeline_control.application.requests.get_invocation_request import (
    GetInvocationRequest,
)
from huginn.pipeline_control.application.responses.get_invocation_response import (
    GetInvocationResponse,
)


class GetInvocationService:
    def __init__(self, reader: InvocationReader) -> None:
        self._reader = reader

    def execute(self, request: GetInvocationRequest) -> GetInvocationResponse:
        invocation = self._reader.get(request.invocation_id)
        if invocation is None:
            raise InvocationNotFoundError("invocation not found")
        return GetInvocationResponse(invocation)
