from typing import Literal

from huginn.management.presentation.api.requests.common import RequestModel


class AllEligibleTargetBody(RequestModel):
    kind: Literal["all_eligible"]
