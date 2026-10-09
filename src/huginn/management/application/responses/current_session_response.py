"""Private session bootstrap value, without the opaque credential."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from huginn.management.domain.value_objects.account_role import AccountRole


@dataclass(frozen=True, slots=True)
class CurrentSessionResponse:
    account_id: UUID
    user_id: UUID
    csrf_token: str = field(repr=False)
    expires_at: datetime
    role: AccountRole = AccountRole("user")
