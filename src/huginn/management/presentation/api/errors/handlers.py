"""FastAPI exception handler functions for the management error contract."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from huginn.management.application.errors.lifecycle import LifecycleRateLimitError
from huginn.management.domain.errors.errors import ManagementDomainError
from huginn.management.persistence.errors.database import DatabaseError, IntegrityError
from huginn.management.presentation.api.errors.shapes import (
    ErrorShape,
    domain_error_shape,
    error_shape_for_status,
    native_validation_shape,
)

logger = logging.getLogger(__name__)


class _SuppressHandledServerError:
    """Stop Starlette's handled 500 from being re-raised to Uvicorn."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        response_started = False

        async def track_response(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_response)
        except Exception as error:
            # ServerErrorMiddleware sends the registered safe response, then
            # re-raises. Suppress only that post-response re-raise; exceptions
            # that prevented a response from starting still reach the server.
            if (
                not response_started
                or scope.get("_management_handled_exception") is not error
            ):
                raise


def sanitized_validation_shape(errors: list[dict[str, Any]]) -> ErrorShape:
    """Build native 422 details without rejected values or internal metadata."""
    details: list[dict[str, Any]] = []
    for item in errors:
        location = item.get("loc", ())
        if item.get("type") == "extra_forbidden":
            location = location[:-1]
        details.append(
            {
                "loc": list(location),
                "type": str(item.get("type", "value_error")),
                "msg": "Invalid value",
            }
        )
    return native_validation_shape(details)


def validation_error_shape(error: RequestValidationError) -> ErrorShape:
    """Map framework validation failures without echoing request values."""
    return sanitized_validation_shape(error.errors())


def _private_headers(request: Request) -> dict[str, str] | None:
    if (
        request.url.path.startswith("/api/v1/admin/")
        or request.url.path == "/api/v1/matches"
        or request.url.path.startswith("/api/v1/matches/")
        or request.url.path == "/api/v1/sessions/current"
        or (
            request.url.path == "/api/v1/configuration-options"
            or request.url.path.startswith("/api/v1/configuration-options/")
        )
    ):
        return {"Cache-Control": "no-store", "Vary": "Cookie"}
    return None


def register_exception_handlers(app: FastAPI) -> None:
    """Register framework handlers; app composition calls this in task 5.9."""

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, error: HTTPException):
        if error.status_code == 503:
            shape = error_shape_for_status(503)
            return JSONResponse(
                status_code=shape.status_code,
                content=shape.body,
                headers={"Cache-Control": "no-store"},
            )
        response = await http_exception_handler(request, error)
        response.headers.update(_private_headers(request) or {})
        return response

    @app.exception_handler(ManagementDomainError)
    async def handle_domain_error(
        request: Request, error: ManagementDomainError
    ) -> JSONResponse:
        shape = domain_error_shape(error)
        headers = _private_headers(request)
        if isinstance(error, LifecycleRateLimitError):
            headers = {
                "Retry-After": str(error.retry_after_seconds),
                "Cache-Control": "no-store",
            }
        return JSONResponse(
            status_code=shape.status_code, content=shape.body, headers=headers
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(
        request: Request, error: IntegrityError
    ) -> JSONResponse:
        route = request.scope.get("route")
        route_template = getattr(route, "path", "<unmatched>")
        logger.warning(
            "Management API integrity conflict on %s %s (%s, SQLSTATE %s)",
            request.method,
            route_template,
            error.error_name,
            error.sqlstate or "<unknown>",
        )
        shape = error_shape_for_status(409)
        return JSONResponse(
            status_code=shape.status_code,
            content=shape.body,
            headers=_private_headers(request),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        shape = validation_error_shape(error)
        return JSONResponse(
            status_code=shape.status_code,
            content=shape.body,
            headers=_private_headers(request),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, error: Exception
    ) -> JSONResponse:
        request.scope["_management_handled_exception"] = error
        route = request.scope.get("route")
        route_template = getattr(route, "path", "<unmatched>")
        logger.error(
            "Unhandled management API exception on %s %s (%s)",
            request.method,
            route_template,
            error.error_name
            if isinstance(error, DatabaseError)
            else type(error).__name__,
        )
        shape = error_shape_for_status(500)
        return JSONResponse(
            status_code=shape.status_code,
            content=shape.body,
            headers=_private_headers(request),
        )


def suppress_handled_server_error_tracebacks(app: FastAPI) -> None:
    """Wrap the completed middleware stack to contain handled 500 exceptions."""
    app.middleware_stack = _SuppressHandledServerError(app.build_middleware_stack())
