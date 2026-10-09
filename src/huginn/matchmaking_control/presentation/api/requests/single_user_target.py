from typing import Literal

from huginn.management.presentation.api.requests.common import RequestModel, RequestUUID


class SingleUserTargetBody(RequestModel):
    kind: Literal["user"]
    user_id: RequestUUID
