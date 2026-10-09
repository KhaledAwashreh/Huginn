"""Authenticated collected-options query input."""

from dataclasses import dataclass

from huginn.management.domain.value_objects.common import Principal


@dataclass(frozen=True)
class GetConfigurationOptionsRequest:
    principal: Principal
