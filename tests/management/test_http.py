import logging
from dataclasses import dataclass
from uuid import UUID

import pytest
from psycopg import IntegrityError
from pydantic import BaseModel, ConfigDict, Field

from huginn.management import app as app_module
from huginn.management.config import ManagementConfig
from huginn.management.domain import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    Page,
    RateLimitError,
    ValidationDomainError,
)
from huginn.management.http import json_response, page_response, parse_json


class Payload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1)


class FakeReadiness:
    def is_ready(self):
        return True


def make_app():
    app = app_module.create_app(ManagementConfig("unused"), readiness=FakeReadiness())

    @app.post("/parse")
    def parse_route():
        return json_response(parse_json(Payload))

    @app.get("/boom")
    def boom_route():
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

    response = app.test_client().get("/error")

    assert response.status_code == status
    assert response.json == {"error": {"code": code, "message": message, "details": []}}
    assert "secret-value" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "body", (b"{", b'{"name":"ok","name":"again"}', b'{"name":NaN}')
)
def test_invalid_or_ambiguous_json_is_bad_request(body):
    response = (
        make_app()
        .test_client()
        .post("/parse", data=body, content_type="application/json")
    )

    assert response.status_code == 400
    assert response.json["error"]["code"] == "malformed_json"


def test_pydantic_validation_is_422_without_echoing_input():
    response = (
        make_app()
        .test_client()
        .post("/parse", json={"name": "secret-value", "extra": True})
    )

    assert response.status_code == 422
    assert response.json["error"]["code"] == "validation_error"
    assert "secret-value" not in response.get_data(as_text=True)


def test_validation_details_do_not_echo_unknown_field_names():
    response = (
        make_app()
        .test_client()
        .post(
            "/parse",
            json={"name": "valid", "password_hash_attacker_secret": "secret-value"},
        )
    )

    assert response.status_code == 422
    assert "password_hash_attacker_secret" not in response.get_data(as_text=True)
    assert "secret-value" not in response.get_data(as_text=True)


def test_valid_json_with_wrong_top_level_shape_is_422():
    response = (
        make_app()
        .test_client()
        .post("/parse", data="null", content_type="application/json")
    )

    assert response.status_code == 422


def test_missing_json_content_type_is_400():
    response = make_app().test_client().post("/parse", data='{"name":"ok"}')

    assert response.status_code == 400
    assert response.json["error"]["code"] == "malformed_json"


def test_generic_500_is_safe_in_response_and_logs(caplog):
    app = make_app()
    caplog.set_level(logging.ERROR)

    response = app.test_client().get("/boom")

    assert response.status_code == 500
    assert response.json == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "details": [],
        }
    }
    assert "do not expose" not in response.get_data(as_text=True)
    assert "secret-value" not in caplog.text


def test_response_serializer_rejects_sensitive_fields_without_echoing_them(caplog):
    app = make_app()

    @app.get("/sensitive")
    def sensitive_route():
        return json_response(
            {
                "profile": {
                    "PASSWORD": "secret-value",
                    "nested": [
                        {"current_password": "current-secret"},
                        {"csrf_digest": "csrf-secret"},
                    ],
                }
            }
        )

    @dataclass(frozen=True)
    class SensitiveRecord:
        new_password: str

    class SensitiveModel(BaseModel):
        password_hash: str

    @app.get("/sensitive-dataclass")
    def sensitive_dataclass_route():
        return json_response(SensitiveRecord("dataclass-secret"))

    @app.get("/sensitive-model")
    def sensitive_model_route():
        return json_response(SensitiveModel(password_hash="model-secret"))

    caplog.set_level(logging.ERROR)
    responses = [
        app.test_client().get(path)
        for path in ("/sensitive", "/sensitive-dataclass", "/sensitive-model")
    ]

    for response in responses:
        assert response.status_code == 500
        assert response.json == {
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "details": [],
            }
        }
        for secret in (
            "secret-value",
            "current-secret",
            "csrf-secret",
            "dataclass-secret",
            "model-secret",
        ):
            assert secret not in response.get_data(as_text=True)
    for secret in (
        "secret-value",
        "current-secret",
        "csrf-secret",
        "dataclass-secret",
        "model-secret",
    ):
        assert secret not in caplog.text
    assert "password" not in caplog.text.casefold()
    assert "csrf_digest" not in caplog.text


def test_database_integrity_failure_maps_to_safe_conflict():
    app = make_app()

    @app.get("/integrity")
    def integrity_route():
        raise IntegrityError("database detail secret-value")

    response = app.test_client().get("/integrity")

    assert response.status_code == 409
    assert response.json["error"]["code"] == "conflict"
    assert "secret-value" not in response.get_data(as_text=True)


def test_unmatched_route_uses_not_found_envelope():
    response = make_app().test_client().get("/not-registered")

    assert response.status_code == 404
    assert response.json["error"]["code"] == "not_found"


@dataclass(frozen=True)
class Item:
    id: UUID
    value: str


def test_page_response_has_stable_shape_and_json_serializes_items():
    page = Page(items=(Item(UUID(int=1), "first"),), offset=10, limit=1, has_more=True)
    app = make_app()

    with app.app_context():
        response, status = page_response(page)

    assert status == 200
    assert response.json == {
        "items": [{"id": "00000000-0000-0000-0000-000000000001", "value": "first"}],
        "offset": 10,
        "limit": 1,
        "has_more": True,
    }
