"""ForgotPasswordRequest strict HTTP body."""

from huginn.management.presentation.api.primitives import Email
from huginn.management.presentation.api.requests.common import RequestModel


class ForgotPasswordRequest(RequestModel):
    email: Email
