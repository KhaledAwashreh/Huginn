"""Login, logout, and password change endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from huginn.management.application.requests.current_session_request import (
    CurrentSessionRequest,
)
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.browser_origin import (
    require_same_origin_browser_mutation,
)
from huginn.management.presentation.api.dependencies.services import (
    Management,
    get_authentication_service,
    get_current_session_service,
    get_login_service,
    get_password_change_service,
)
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.authentication import (
    LoginRequest,
    PasswordChangeRequest,
)
from huginn.management.presentation.api.responses.authentication import LoginResponse
from huginn.management.presentation.api.responses.current_session import (
    CurrentSessionResponse,
)

router = APIRouter(prefix="/api/v1", tags=["sessions"])


def _set_session_cookie(response: Response, dependencies: Any, token: str) -> None:
    config = dependencies.config
    response.set_cookie(
        config.cookie_name,
        token,
        max_age=max(0, int(config.session_ttl.total_seconds())),
        path="/",
        secure=bool(config.cookie_secure),
        httponly=True,
        samesite=config.cookie_samesite,
    )


def _clear_session_cookie(response: Response, dependencies: Any) -> None:
    config = dependencies.config
    response.delete_cookie(
        config.cookie_name,
        path="/",
        secure=bool(config.cookie_secure),
        httponly=True,
        samesite=config.cookie_samesite,
    )


@router.post(
    "/sessions",
    response_model=LoginResponse,
    responses=error_responses(400, 401, 403, 422, 429),
    dependencies=[Depends(require_same_origin_browser_mutation)],
)
def create_session(
    body: LoginRequest,
    request: Request,
    response: Response,
    dependencies: Management,
    service: Annotated[Any, Depends(get_login_service)],
) -> LoginResponse:
    issued = service.login(
        username=body.username,
        password=body.password,
        client_ip=request.client.host if request.client else "",
    )
    _set_session_cookie(response, dependencies, issued.session_token)
    return LoginResponse(csrf_token=issued.csrf_token, expires_at=issued.expires_at)


@router.delete(
    "/sessions/current",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 422),
)
def delete_current_session(
    authenticated: CsrfProtected,
    dependencies: Management,
    service: Annotated[Any, Depends(get_authentication_service)],
    response: Response,
) -> Response:
    service.logout(authenticated.token)
    _clear_session_cookie(response, dependencies)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.patch(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 401, 403, 422),
)
def change_current_password(
    body: PasswordChangeRequest,
    authenticated: CsrfProtected,
    service: Annotated[Any, Depends(get_password_change_service)],
    dependencies: Management,
    response: Response,
) -> Response:
    service.change_password(
        authenticated.principal.account_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    _clear_session_cookie(response, dependencies)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/sessions/current",
    response_model=CurrentSessionResponse,
    responses=error_responses(401),
)
def get_current_session(
    authenticated: Authenticated,
    service: Annotated[Any, Depends(get_current_session_service)],
    response: Response,
) -> CurrentSessionResponse:
    result = service.execute(
        CurrentSessionRequest(
            authenticated.principal,
            authenticated.session.id,
            authenticated.token,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return CurrentSessionResponse(
        account_id=result.account_id,
        user_id=result.user_id,
        csrf_token=result.csrf_token,
        expires_at=result.expires_at,
    )
