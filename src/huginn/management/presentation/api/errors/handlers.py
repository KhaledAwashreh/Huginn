"""FastAPI exception handler functions for the management error contract."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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


def register_exception_handlers(app: FastAPI) -> None:
    """Register framework handlers; app composition calls this in task 5.9."""

    @app.exception_handler(ManagementDomainError)
    async def handle_domain_error(
        request: Request, error: ManagementDomainError
    ) -> JSONResponse:
        shape = domain_error_shape(error)
        headers = (
            {"Cache-Control": "no-store", "Vary": "Cookie"}
            if request.url.path == "/api/v1/sessions/current"
            else None
        )
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
        return JSONResponse(status_code=shape.status_code, content=shape.body)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request
        shape = validation_error_shape(error)
        return JSONResponse(status_code=shape.status_code, content=shape.body)

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
        return JSONResponse(status_code=shape.status_code, content=shape.body)


def suppress_handled_server_error_tracebacks(app: FastAPI) -> None:
    """Wrap the completed middleware stack to contain handled 500 exceptions."""
    app.middleware_stack = _SuppressHandledServerError(app.build_middleware_stack())
