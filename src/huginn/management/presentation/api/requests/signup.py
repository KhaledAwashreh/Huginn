"""SignupRequest strict HTTP body."""

from pydantic import Field, ValidationInfo, field_validator

from huginn.management.application.constants.lifecycle_policy import (
    COUNTRY_CALLING_CODES,
)
from huginn.management.presentation.api.primitives import (
    E164Phone,
    Email,
    IanaTimezone,
    NonBlankText,
)
from huginn.management.presentation.api.requests.common import RequestModel
from huginn.management.security.password_policy import (
    NEW_PASSWORD_MAX_LENGTH,
    NEW_PASSWORD_MIN_LENGTH,
)
from huginn.management.security.passwords import validate_new_password


class SignupRequest(RequestModel):
    username: NonBlankText = Field(repr=False)
    password: str = Field(
        min_length=NEW_PASSWORD_MIN_LENGTH,
        max_length=NEW_PASSWORD_MAX_LENGTH,
        repr=False,
    )
    first_name: NonBlankText
    last_name: NonBlankText
    email: Email = Field(repr=False)
    phone_number: E164Phone = Field(repr=False)
    country_of_residence: NonBlankText
    timezone: IanaTimezone | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_new_password(value).value

    @field_validator("country_of_residence")
    @classmethod
    def validate_country(cls, value: str, info: ValidationInfo) -> str:
        if value not in COUNTRY_CALLING_CODES:
            raise ValueError("Select a country of residence")
        phone = info.data.get("phone_number")
        prefix = COUNTRY_CALLING_CODES[value]
        if phone is not None and (
            not phone.startswith(prefix) or len(phone) - len(prefix) < 3
        ):
            raise ValueError("Phone prefix must match the selected country")
        return value
