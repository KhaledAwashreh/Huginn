import asyncio
import logging
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import errors
from pydantic import BaseModel, ConfigDict
from uvicorn.protocols.http.h11_impl import RequestResponseCycle

from huginn.management.errors.domain import ConflictError
from huginn.management.errors.handlers import (
    register_exception_handlers,
    suppress_handled_server_error_tracebacks,
)


class Credentials(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    password: str


def make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/domain")
    def domain_failure():
        raise ConflictError("private detail secret-sentinel")

    @app.get("/integrity")
    def integrity_failure():
        raise errors.UniqueViolation("constraint detail token-sentinel")

    @app.post("/validate")
    def validate(credentials: Credentials):
        return {"accepted": bool(credentials.password)}

    @app.post("/unexpected")
    def unexpected(credentials: Credentials):
        raise RuntimeError(f"failure for {credentials.password} with token-sentinel")

    return app


def test_domain_and_integrity_failures_use_safe_project_envelopes(caplog):
    caplog.set_level(logging.ERROR)
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        domain = client.get("/domain")
        integrity = client.get("/integrity")

    assert domain.status_code == 409
    assert domain.json() == {
        "error": {
            "code": "conflict",
            "message": "Request could not be completed",
            "details": [],
        }
    }
    assert "secret-sentinel" not in domain.text
    assert "secret-sentinel" not in caplog.text
    assert integrity.status_code == 409
    assert integrity.json() == {
        "error": {
            "code": "conflict",
            "message": "Request could not be completed",
            "details": [],
        }
    }
    assert "token-sentinel" not in integrity.text
    assert "token-sentinel" not in caplog.text


def test_integrity_failure_logs_safe_request_and_database_metadata(caplog):
    caplog.set_level(logging.WARNING)
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        response = client.get("/integrity")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "Request could not be completed",
            "details": [],
        }
    }
    assert "GET /integrity" in caplog.text
    assert "UniqueViolation" in caplog.text
    assert "23505" in caplog.text
    assert "constraint detail" not in caplog.text
    assert "token-sentinel" not in caplog.text


def test_validation_is_native_sanitized_and_does_not_log_secrets(caplog):
    caplog.set_level(logging.ERROR)
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/validate",
            json={"password": "password-sentinel", "extra": "token-sentinel"},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body"]
    assert "password-sentinel" not in response.text
    assert "token-sentinel" not in response.text
    assert "password-sentinel" not in caplog.text
    assert "token-sentinel" not in caplog.text


def test_framework_404_and_405_keep_native_starlette_conventions():
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        missing = client.get("/missing")
        wrong_method = client.post("/domain")

    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}
    assert wrong_method.status_code == 405
    assert wrong_method.json() == {"detail": "Method Not Allowed"}


def test_unexpected_500_logs_safe_route_context_without_secrets(caplog):
    caplog.set_level(logging.ERROR)
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        response = client.post("/unexpected", json={"password": "password-sentinel"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "details": [],
        }
    }
    assert "password-sentinel" not in response.text
    assert "token-sentinel" not in response.text
    assert "password-sentinel" not in caplog.text
    assert "token-sentinel" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "POST /unexpected" in caplog.text


def test_unexpected_500_does_not_escape_to_uvicorn_traceback_logging(caplog):
    app = make_app()

    @app.get("/secret")
    async def secret_failure():
        raise RuntimeError("failure for password-sentinel with token-sentinel")

    suppress_handled_server_error_tracebacks(app)
    sent: list[dict] = []

    class UvicornProtocolHarness:
        """Supply the ASGI pieces consumed by Uvicorn's real run_asgi method."""

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/secret",
            "raw_path": b"/secret",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
        }
        logger = logging.getLogger("uvicorn.error")
        response_started = False
        response_complete = False
        disconnected = False
        transport = SimpleNamespace(close=lambda: None)

        def on_response():
            pass

        async def receive(self):
            return {"type": "http.disconnect"}

        async def send(self, message):
            if message["type"] == "http.response.start":
                self.response_started = True
            elif message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                self.response_complete = True
            sent.append(message)

    caplog.set_level(logging.ERROR, logger="uvicorn.error")
    protocol = UvicornProtocolHarness()
    asyncio.run(
        asyncio.wait_for(RequestResponseCycle.run_asgi(protocol, app), timeout=2)
    )

    response_start = next(
        item for item in sent if item["type"] == "http.response.start"
    )
    response_body = b"".join(
        item.get("body", b"") for item in sent if item["type"] == "http.response.body"
    )
    assert response_start["status"] == 500
    assert b'"code":"internal_error"' in response_body
    assert b"password-sentinel" not in response_body
    assert b"token-sentinel" not in response_body
    assert "password-sentinel" not in caplog.text
    assert "token-sentinel" not in caplog.text
    assert "Exception in ASGI application" not in caplog.text
    assert "RuntimeError: failure for" not in caplog.text
