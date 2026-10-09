"""Administrator-only API dependency."""

from typing import Annotated

from fastapi import Depends

from huginn.management.application.errors.errors import AuthorizationError
from huginn.management.domain.value_objects.account_role import AccountRole
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    AuthenticatedSession,
)


def require_administrator(
    authenticated: Authenticated,
) -> AuthenticatedSession:
    if authenticated.principal.role != AccountRole("admin"):
        raise AuthorizationError("administrator role is required")
    return authenticated


Administrator = Annotated[AuthenticatedSession, Depends(require_administrator)]
