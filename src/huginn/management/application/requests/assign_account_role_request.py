"""Trusted operator request to change an account role."""

from dataclasses import dataclass

from huginn.management.domain.value_objects.account_role import AccountRole


@dataclass(frozen=True, slots=True)
class AssignAccountRoleRequest:
    username: str
    role: AccountRole
