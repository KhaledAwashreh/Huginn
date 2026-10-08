"""Authenticated lifecycle application request."""

from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True, slots=True)
class GetAccountSecurityRequest:
    principal: Principal
