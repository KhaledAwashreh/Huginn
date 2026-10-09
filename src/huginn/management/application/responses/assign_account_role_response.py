"""Result of a trusted account role assignment."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.value_objects.account_role import AccountRole


@dataclass(frozen=True, slots=True)
class AssignAccountRoleResponse:
    account_id: UUID
    username: str
    role: AccountRole
