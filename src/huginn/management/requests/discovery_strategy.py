"""Discovery strategy request models."""

from typing import Self

from pydantic import model_validator

from huginn.management.primitives import NonBlankText
from huginn.management.requests.common import (
    NonBlank,
    PatchRequest,
    RequestModel,
    RequestUUID,
)


class DiscoveryStrategyCreateRequest(RequestModel):
    name: NonBlank
    service_offering_id: RequestUUID
    ideal_client_profile_id: RequestUUID
    is_active: bool = False


class DiscoveryStrategyUpdateRequest(PatchRequest):
    name: NonBlankText | None = None
    service_offering_id: RequestUUID | None = None
    ideal_client_profile_id: RequestUUID | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def supplied_values_cannot_be_null(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
