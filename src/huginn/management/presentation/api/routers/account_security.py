"""Authenticated account security read and initial recovery enrollment."""

from fastapi import APIRouter, Depends, Response

from huginn.management.application.requests.enroll_recovery_email_request import (
    EnrollRecoveryEmailRequest as EnrollApplicationRequest,
)
from huginn.management.application.requests.get_account_security_request import (
    GetAccountSecurityRequest,
)
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.browser_origin import (
    require_same_origin_browser_mutation,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.enroll_recovery_email import (
    EnrollRecoveryEmailRequest,
)
from huginn.management.presentation.api.responses.account_security import (
    AccountSecurityResponse,
)
from huginn.management.presentation.api.responses.lifecycle_receipt import (
    LifecycleReceiptResponse,
)
from huginn.management.presentation.api.routers.account_lifecycle import (
    require_delivery_configuration,
)

router = APIRouter(prefix="/api/v1/me", tags=["account security"])


@router.get(
    "/account-security",
    response_model=AccountSecurityResponse,
    responses=error_responses(401, 403),
)
def get_account_security(
    authenticated: Authenticated, response: Response, dependencies: Management
) -> AccountSecurityResponse:
    security = dependencies.get_account_security_service.execute(
        GetAccountSecurityRequest(authenticated.principal)
    ).security
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return AccountSecurityResponse(
        username=security.username,
        email_verification_required=security.email_verification_required,
        email_verified=security.email_verified,
        recovery_email=security.recovery_email,
    )


@router.post(
    "/recovery-email-verifications",
    status_code=202,
    response_model=LifecycleReceiptResponse,
    responses=error_responses(401, 403, 409, 422, 503),
    dependencies=[
        Depends(require_same_origin_browser_mutation),
        Depends(require_delivery_configuration),
    ],
)
def enroll_recovery_email(
    body: EnrollRecoveryEmailRequest,
    authenticated: CsrfProtected,
    response: Response,
    dependencies: Management,
) -> LifecycleReceiptResponse:
    del body
    result = dependencies.enroll_recovery_email_service.execute(
        EnrollApplicationRequest(authenticated.principal)
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return LifecycleReceiptResponse(message=result.message)
