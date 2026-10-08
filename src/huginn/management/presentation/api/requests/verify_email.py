"""VerifyEmailRequest strict HTTP body."""

from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel


class VerifyEmailRequest(RequestModel):
    token: str = Field(min_length=1, max_length=1024, repr=False)
