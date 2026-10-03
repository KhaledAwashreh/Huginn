"""Current User request models."""

from typing import Self

from pydantic import model_validator

from huginn.management.primitives import E164Phone, Email, IanaTimezone, NonBlankText
from huginn.management.requests.common import PatchRequest


class UserUpdateRequest(PatchRequest):
    first_name: NonBlankText | None = None
    last_name: NonBlankText | None = None
    email: Email | None = None
    phone_number: E164Phone | None = None
    country_of_residence: NonBlankText | None = None
    timezone: IanaTimezone | None = None

    @model_validator(mode="after")
    def required_values_cannot_be_null(self) -> Self:
        for field in self.model_fields_set - {"timezone"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
