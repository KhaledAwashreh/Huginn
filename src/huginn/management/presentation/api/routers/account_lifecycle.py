"""Public account lifecycle endpoints; lifecycle design section 3."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from huginn.management.application.requests.forgot_password_request import (
    ForgotPasswordRequest as ForgotPasswordApplicationRequest,
)
from huginn.management.application.requests.resend_verification_request import (
    ResendVerificationRequest as ResendVerificationApplicationRequest,
)
from huginn.management.application.requests.reset_password_request import (
    ResetPasswordRequest as ResetPasswordApplicationRequest,
)
from huginn.management.application.requests.signup_request import (
    SignupRequest as SignupApplicationRequest,
)
from huginn.management.application.requests.verify_email_request import (
    VerifyEmailRequest as VerifyEmailApplicationRequest,
)
from huginn.management.presentation.api.dependencies.browser_origin import (
    require_same_origin_browser_mutation,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.forgot_password import (
    ForgotPasswordRequest,
)
from huginn.management.presentation.api.requests.resend_verification import (
    ResendVerificationRequest,
)
from huginn.management.presentation.api.requests.reset_password import (
    ResetPasswordRequest,
)
from huginn.management.presentation.api.requests.signup import SignupRequest
from huginn.management.presentation.api.requests.verify_email import VerifyEmailRequest
from huginn.management.presentation.api.responses.lifecycle_receipt import (
    LifecycleReceiptResponse,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["account lifecycle"],
    dependencies=[Depends(require_same_origin_browser_mutation)],
)


def require_delivery_configuration(dependencies: Management) -> None:
    if (
        not dependencies.config.lifecycle_proof_key
        or not dependencies.config.web_origin
    ):
        raise HTTPException(
            status_code=503, detail="Account requests are temporarily unavailable"
        )


def _private_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.post(
    "/accounts",
    status_code=202,
    response_model=LifecycleReceiptResponse,
    responses=error_responses(403, 422, 429, 503),
    dependencies=[Depends(require_delivery_configuration)],
)
def signup(
    body: SignupRequest, request: Request, response: Response, dependencies: Management
) -> LifecycleReceiptResponse:
    result = dependencies.signup_service.execute(
        SignupApplicationRequest(
            username=body.username,
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone_number=body.phone_number,
            country_of_residence=body.country_of_residence,
            timezone=body.timezone,
            client_ip=_client_ip(request),
        )
    )
    _private_headers(response)
    return LifecycleReceiptResponse(message=result.message)


@router.post(
    "/email-verifications", status_code=204, responses=error_responses(403, 422, 429)
)
def verify_email(
    body: VerifyEmailRequest, request: Request, dependencies: Management
) -> Response:
    dependencies.verify_email_service.execute(
        VerifyEmailApplicationRequest(body.token, _client_ip(request))
    )
    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post(
    "/email-verifications/resend",
    status_code=202,
    response_model=LifecycleReceiptResponse,
    responses=error_responses(403, 422, 429, 503),
    dependencies=[Depends(require_delivery_configuration)],
)
def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    response: Response,
    dependencies: Management,
) -> LifecycleReceiptResponse:
    result = dependencies.resend_verification_service.execute(
        ResendVerificationApplicationRequest(body.email, _client_ip(request))
    )
    _private_headers(response)
    return LifecycleReceiptResponse(message=result.message)


@router.post(
    "/password-resets",
    status_code=202,
    response_model=LifecycleReceiptResponse,
    responses=error_responses(403, 422, 429, 503),
    dependencies=[Depends(require_delivery_configuration)],
)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    response: Response,
    dependencies: Management,
) -> LifecycleReceiptResponse:
    result = dependencies.forgot_password_service.execute(
        ForgotPasswordApplicationRequest(body.email, _client_ip(request))
    )
    _private_headers(response)
    return LifecycleReceiptResponse(message=result.message)


@router.post(
    "/password-resets/complete",
    status_code=204,
    responses=error_responses(403, 422, 429),
)
def reset_password(
    body: ResetPasswordRequest, request: Request, dependencies: Management
) -> Response:
    dependencies.reset_password_service.execute(
        ResetPasswordApplicationRequest(
            body.token, body.new_password, _client_ip(request)
        )
    )
    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
