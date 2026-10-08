"""ResendVerificationRequest strict HTTP body."""

from huginn.management.presentation.api.primitives import Email
from huginn.management.presentation.api.requests.common import RequestModel


class ResendVerificationRequest(RequestModel):
    email: Email
