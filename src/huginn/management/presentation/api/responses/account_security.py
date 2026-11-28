"""AccountSecurityResponse HTTP projection."""

from pydantic import Field

from huginn.management.presentation.api.responses.common import ResponseModel


class AccountSecurityResponse(ResponseModel):
    account_email: str = Field(repr=False)
    pending_email: str | None = Field(repr=False)
    email_verification_required: bool
    email_verified: bool
