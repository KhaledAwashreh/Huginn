"""Authenticated lifecycle application request."""

from dataclasses import dataclass, field

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True, slots=True)
class EnrollRecoveryEmailRequest:
    principal: Principal
    email: str | None = field(default=None, repr=False)
    current_password: str | None = field(default=None, repr=False)
    client_ip: str = field(default="", repr=False)
