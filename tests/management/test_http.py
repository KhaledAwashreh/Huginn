"""FastAPI boundary checks for the public management error contract."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from huginn.management.errors.domain import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ValidationDomainError,
)
from huginn.management.errors.handlers import register_exception_handlers


class Payload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1)


def make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/parse")
    def parse_route(payload: Payload) -> Payload:
        return payload

    @app.get("/boom")
    def boom_route() -> None:
        raise RuntimeError("do not expose this exception or secret-value")

    return app


@pytest.mark.parametrize(
    ("error", "status", "code", "message"),
    (
        (
            AuthenticationError("credentials secret-value"),
            401,
            "authentication_error",
            "Request could not be completed",
        ),
        (
            AuthorizationError("csrf secret-value"),
            403,
            "authorization_error",
            "Request could not be completed",
        ),
        (
            NotFoundError("resource secret-value"),
            404,
            "not_found",
            "Request could not be completed",
        ),
        (
            ConflictError("duplicate secret-value"),
            409,
            "conflict",
            "Request could not be completed",
        ),
        (
            ValidationDomainError("invalid secret-value"),
            422,
            "validation_error",
            "Request validation failed",
        ),
        (
            RateLimitError("throttle secret-value"),
            429,
            "rate_limited",
            "Request could not be completed",
        ),
    ),
)
def test_domain_errors_have_stable_safe_envelopes(error, status, code, message):
    app = make_app()

    @app.get("/error")
    def raise_error():
        raise error

    response = TestClient(app).get("/error")

    assert response.status_code == status
    assert response.json() == {
        "error": {"code": code, "message": message, "details": []}
    }
    assert "secret-value" not in response.text


@pytest.mark.parametrize("body", (b"{", b'{"name":NaN}'))
def test_malformed_json_is_rejected_without_echoing_body(body):
    response = TestClient(make_app()).post(
        "/parse", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert "secret-value" not in response.text


def test_pydantic_validation_is_422_without_echoing_input():
    response = TestClient(make_app()).post(
        "/parse", json={"name": "secret-value", "extra": True}
    )

    assert response.status_code == 422
    assert "secret-value" not in response.text


def test_validation_details_do_not_echo_unknown_field_names():
    response = TestClient(make_app()).post(
        "/parse",
        json={"name": "valid", "password_hash_attacker_secret": "secret-value"},
    )

    assert response.status_code == 422
    assert "password_hash_attacker_secret" not in response.text
    assert "secret-value" not in response.text


def test_missing_json_content_type_is_parsed_by_fastapi():
    response = TestClient(make_app()).post("/parse", content='{"name":"ok"}')

    assert response.status_code == 422


def test_generic_500_is_safe_in_response_and_logs(caplog):
    caplog.set_level(logging.ERROR)
    response = TestClient(make_app(), raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "details": [],
        }
    }
    assert "do not expose" not in response.text
    assert "secret-value" not in caplog.text
