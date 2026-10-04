"""Server-side session and session-bound CSRF dependencies."""

import hmac
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, Request, Security
from fastapi.security import APIKeyCookie

from huginn.management.application.errors.errors import (
    AuthenticationError,
    AuthorizationError,
)
from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.common import Principal
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.security.tokens import digest_token

_SESSION_COOKIE = APIKeyCookie(
    name="huginn_management_session", auto_error=False, scheme_name="SessionCookie"
)


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    principal: Principal
    session: Session
    token: str = field(repr=False)


def get_authenticated_session(
    request: Request,
    dependencies: Management,
    token: Annotated[str | None, Security(_SESSION_COOKIE)],
) -> AuthenticatedSession:
    cookie_name = dependencies.config.cookie_name
    # APIKeyCookie keeps the OpenAPI security scheme, but its static default
    # name must never act as an alternate credential when config is customized.
    del token
    token = request.cookies.get(cookie_name)
    if not token:
        raise AuthenticationError("authentication required")
    authenticated = dependencies.authentication_service.authenticate_session(token)
    if authenticated is None:
        raise AuthenticationError("authentication required")
    return AuthenticatedSession(authenticated.principal, authenticated.session, token)


Authenticated = Annotated[AuthenticatedSession, Depends(get_authenticated_session)]


def require_csrf(
    request: Request,
    authenticated: Authenticated,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthenticatedSession:
    if request.method.upper() in {"POST", "PATCH", "PUT", "DELETE"}:
        supplied = digest_token(csrf_token or "")
        if not csrf_token or not hmac.compare_digest(
            supplied, authenticated.session.csrf_digest
        ):
            raise AuthorizationError("valid CSRF proof is required")
    return authenticated


CsrfProtected = Annotated[AuthenticatedSession, Depends(require_csrf)]
