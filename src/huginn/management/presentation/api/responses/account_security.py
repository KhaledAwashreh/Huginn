"""AccountSecurityResponse HTTP projection."""

from pydantic import Field

from huginn.management.presentation.api.responses.common import ResponseModel


class AccountSecurityResponse(ResponseModel):
    username: str
    email_verification_required: bool
    email_verified: bool
    recovery_email: str | None = Field(repr=False)
