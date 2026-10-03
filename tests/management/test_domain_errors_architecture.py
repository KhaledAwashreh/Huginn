import ast
import asyncio
import importlib
import inspect
import json

import pytest

DOMAIN_MODULES = (
    "__init__",
    "common",
    "account",
    "user",
    "professional_profile",
    "session",
    "service_offering",
    "ideal_client_profile",
    "client_discovery_strategy",
)


@pytest.mark.parametrize("module_name", DOMAIN_MODULES)
def test_domain_resource_modules_have_no_transport_or_infrastructure_imports(
    module_name,
):
    module = importlib.import_module(f"huginn.management.domain.{module_name}")
    syntax = ast.parse(inspect.getsource(module))
    imported = {
        alias.name
        for node in ast.walk(syntax)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(syntax)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    prohibited_roots = {
        "fastapi",
        "starlette",
        "psycopg",
        "requests",
        "request",
        "response",
    }
    assert not {name for name in imported if name.split(".")[0] in prohibited_roots}


def test_domain_values_are_defined_in_entity_modules_without_package_reexports():
    from huginn.management import domain
    from huginn.management.domain.account import Account, NewAccount
    from huginn.management.domain.common import Page, Principal
    from huginn.management.domain.user import User

    assert all(
        not hasattr(domain, name)
        for name in ("Account", "NewAccount", "Page", "Principal", "User")
    )
    assert NewAccount.__module__ == "huginn.management.domain.account"
    assert Page.__module__ == "huginn.management.domain.common"
    assert Principal.__module__ == "huginn.management.domain.common"
    assert Account.__module__ == "huginn.management.domain.account"
    assert User.__module__ == "huginn.management.domain.user"


def test_domain_errors_are_separate_from_transport_and_keep_stable_hierarchy():
    from huginn.management.errors.domain import (
        ConflictError,
        ManagementDomainError,
        NotFoundError,
    )
    from huginn.management.errors.domain import (
        ConflictError as CanonicalConflictError,
    )
    from huginn.management.errors.domain import (
        ManagementDomainError as CanonicalManagementDomainError,
    )
    from huginn.management.errors.domain import (
        NotFoundError as CanonicalNotFoundError,
    )

    assert ConflictError is CanonicalConflictError
    assert ManagementDomainError is CanonicalManagementDomainError
    assert NotFoundError is CanonicalNotFoundError
    assert issubclass(ConflictError, ManagementDomainError)
    assert str(ConflictError("already exists")) == "already exists"


@pytest.mark.parametrize(
    ("exception_name", "status", "code"),
    (
        ("AuthenticationError", 401, "authentication_error"),
        ("AuthorizationError", 403, "authorization_error"),
        ("NotFoundError", 404, "not_found"),
        ("ConflictError", 409, "conflict"),
        ("ValidationDomainError", 422, "validation_error"),
        ("RateLimitError", 429, "rate_limited"),
        ("ManagementDomainError", 500, "internal_error"),
    ),
)
def test_domain_error_shape_mapping_is_stable(exception_name, status, code):
    from huginn.management.errors.domain import ManagementDomainError
    from huginn.management.errors.shapes import domain_error_shape

    error_type = getattr(
        importlib.import_module("huginn.management.errors.domain"), exception_name
    )
    shape = domain_error_shape(error_type("private detail"))
    assert shape.status_code == status
    assert shape.body["error"]["code"] == code
    assert "private detail" not in str(shape.body)
    assert isinstance(error_type("private detail"), ManagementDomainError)


def test_framework_error_mapping_uses_sanitized_details():
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from starlette.requests import Request

    from huginn.management.errors.handlers import (
        register_exception_handlers,
        validation_error_shape,
    )

    error = RequestValidationError(
        [
            {
                "type": "string_too_short",
                "loc": ("body", "password"),
                "msg": "String should have at least 1 character",
                "input": "do-not-return-this-password",
                "ctx": {"limit_value": 1},
            }
        ]
    )
    shape = validation_error_shape(error)
    assert shape.status_code == 422
    assert shape.body == {
        "detail": [
            {
                "loc": ["body", "password"],
                "type": "string_too_short",
                "msg": "Invalid value",
            }
        ]
    }
    assert "input" not in str(shape.body)
    assert "ctx" not in str(shape.body)
    assert "url" not in str(shape.body)

    app = FastAPI()
    register_exception_handlers(app)
    handler = app.exception_handlers[RequestValidationError]
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/login",
            "raw_path": b"/login",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )
    response = asyncio.run(handler(request, error))
    assert response.status_code == 422
    assert json.loads(response.body) == shape.body


def test_registering_handlers_preserves_native_starlette_http_exceptions():
    from fastapi import FastAPI
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from huginn.management.errors.handlers import register_exception_handlers

    app = FastAPI()
    default_http_exception_handler = app.exception_handlers[StarletteHTTPException]
    register_exception_handlers(app)

    assert (
        app.exception_handlers[StarletteHTTPException] is default_http_exception_handler
    )


def test_registered_fastapi_handlers_return_the_domain_error_shape():
    from fastapi import FastAPI
    from starlette.requests import Request

    from huginn.management.errors.domain import (
        AuthenticationError,
        ManagementDomainError,
    )
    from huginn.management.errors.handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    handler = app.exception_handlers[ManagementDomainError]
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/private",
            "raw_path": b"/private",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )
    response = asyncio.run(handler(request, AuthenticationError("secret detail")))

    assert response.status_code == 401
    assert json.loads(response.body) == {
        "error": {
            "code": "authentication_error",
            "message": "Request could not be completed",
            "details": [],
        }
    }
    assert b"secret detail" not in response.body
