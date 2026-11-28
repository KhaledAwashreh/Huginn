"""Trusted operator request to change an account role."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.account_role import AccountRole


@dataclass(frozen=True, slots=True)
class AssignAccountRoleRequest:
    account_id: UUID
    role: AccountRole
