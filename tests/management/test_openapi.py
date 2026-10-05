from fastapi import FastAPI
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.presentation.api.errors.handlers import (
    register_exception_handlers,
)
from huginn.management.presentation.api.openapi.responses import error_responses


def _document(config: ManagementConfig | None = None) -> dict:
    app = create_app(
        config or ManagementConfig("unused", environment="test"),
        readiness=type("Ready", (), {"is_ready": lambda self: True})(),
    )
    return TestClient(app).get("/openapi.json").json()


def test_openapi_covers_registered_paths_methods_models_and_errors():
    document = _document()
    expected = {
        "/health": {"get"},
        "/ready": {"get"},
        "/api/v1/sessions": {"post"},
        "/api/v1/sessions/current": {"delete"},
        "/api/v1/me": {"get", "patch"},
        "/api/v1/me/password": {"patch"},
        "/api/v1/me/professional-profile": {"get", "patch"},
        "/api/v1/offerings": {"get", "post"},
        "/api/v1/offerings/{offering_id}": {"delete", "get", "patch"},
        "/api/v1/ideal-client-profiles": {"get", "post"},
        "/api/v1/ideal-client-profiles/{profile_id}": {
            "delete",
            "get",
            "patch",
        },
        "/api/v1/discovery-strategies": {"get", "post"},
        "/api/v1/discovery-strategies/{strategy_id}": {
            "delete",
            "get",
            "patch",
        },
    }
    assert {
        path: set(operations) for path, operations in document["paths"].items()
    } == expected

    schemas = document["components"]["schemas"]
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            assert "operationId" in operation
            assert "responses" in operation
            assert "default" in operation["responses"]
            if path.startswith("/api/") and path != "/api/v1/sessions":
                assert any("SessionCookie" in item for item in operation["security"])
                if method in {"post", "patch", "put", "delete"}:
                    assert any("csrfHeader" in item for item in operation["security"])
                    assert any(
                        parameter.get("name") == "X-CSRF-Token"
                        and parameter.get("in") == "header"
                        for parameter in operation.get("parameters", [])
                    )
            if method in {"post", "patch"} and path not in {
                "/api/v1/sessions",
                "/api/v1/sessions/current",
            }:
                assert "requestBody" in operation
                ref = operation["requestBody"]["content"]["application/json"]["schema"][
                    "$ref"
                ]
                assert ref.rsplit("/", 1)[1] in schemas
            for code, response in operation["responses"].items():
                if code in {"400", "401", "403", "404", "409", "429"}:
                    shape = response["content"]["application/json"]["schema"]
                    assert shape["required"] == ["error"]
                if code == "422":
                    shape = response["content"]["application/json"]["schema"]
                    assert {tuple(branch["required"]) for branch in shape["oneOf"]} == {
                        ("detail",),
                        ("error",),
                    }
                    assert "input" not in str(shape)

    for path, method in (
        ("/api/v1/offerings/{offering_id}", "get"),
        ("/api/v1/ideal-client-profiles/{profile_id}", "patch"),
        ("/api/v1/discovery-strategies/{strategy_id}", "delete"),
    ):
        assert any(
            parameter["in"] == "path" and parameter["schema"].get("format") == "uuid"
            for parameter in document["paths"][path][method]["parameters"]
        )

    query_parameters = document["paths"]["/api/v1/offerings"]["get"]["parameters"]
    by_name = {parameter["name"]: parameter for parameter in query_parameters}
    assert by_name["limit"]["schema"]["minimum"] == 1
    assert by_name["limit"]["schema"]["maximum"] == 100
    assert by_name["limit"]["schema"]["default"] == 50
    assert by_name["offset"]["schema"]["minimum"] == 0
    assert by_name["offset"]["schema"]["maximum"] == 9_223_372_036_854_775_807


def test_openapi_documents_every_success_response_model():
    document = _document()
    expected = {
        ("/api/v1/sessions", "post", "200"): "LoginResponse",
        ("/api/v1/me", "get", "200"): "UserResponse",
        ("/api/v1/me", "patch", "200"): "UserResponse",
        (
            "/api/v1/me/professional-profile",
            "get",
            "200",
        ): "ProfessionalProfileResponse",
        (
            "/api/v1/me/professional-profile",
            "patch",
            "200",
        ): "ProfessionalProfileResponse",
        (
            "/api/v1/offerings",
            "get",
            "200",
        ): "PageResponse_ServiceOfferingResponse_",
        ("/api/v1/offerings", "post", "201"): "ServiceOfferingResponse",
        (
            "/api/v1/offerings/{offering_id}",
            "get",
            "200",
        ): "ServiceOfferingResponse",
        (
            "/api/v1/offerings/{offering_id}",
            "patch",
            "200",
        ): "ServiceOfferingResponse",
        (
            "/api/v1/ideal-client-profiles",
            "get",
            "200",
        ): "PageResponse_IdealClientProfileResponse_",
        (
            "/api/v1/ideal-client-profiles",
            "post",
            "201",
        ): "IdealClientProfileResponse",
        (
            "/api/v1/ideal-client-profiles/{profile_id}",
            "get",
            "200",
        ): "IdealClientProfileResponse",
        (
            "/api/v1/ideal-client-profiles/{profile_id}",
            "patch",
            "200",
        ): "IdealClientProfileResponse",
        (
            "/api/v1/discovery-strategies",
            "get",
            "200",
        ): "PageResponse_DiscoveryStrategyResponse_",
        (
            "/api/v1/discovery-strategies",
            "post",
            "201",
        ): "DiscoveryStrategyResponse",
        (
            "/api/v1/discovery-strategies/{strategy_id}",
            "get",
            "200",
        ): "DiscoveryStrategyResponse",
        (
            "/api/v1/discovery-strategies/{strategy_id}",
            "patch",
            "200",
        ): "DiscoveryStrategyResponse",
    }

    actual = {}
    for path, method, status in expected:
        schema = document["paths"][path][method]["responses"][status]["content"][
            "application/json"
        ]["schema"]
        actual[path, method, status] = schema["$ref"].rsplit("/", 1)[1]

    assert actual == expected


def test_openapi_documents_configured_session_cookie_and_clearing():
    document = _document(
        ManagementConfig(
            "unused",
            cookie_name="custom_session",
            cookie_secure=True,
            cookie_samesite="Strict",
            environment="test",
        )
    )
    schemes = document["components"]["securitySchemes"]
    assert schemes["SessionCookie"]["in"] == "cookie"
    assert schemes["SessionCookie"]["name"] == "custom_session"
    assert schemes["csrfHeader"]["in"] == "header"
    assert schemes["csrfHeader"]["name"] == "X-CSRF-Token"

    login = document["paths"]["/api/v1/sessions"]["post"]["responses"]["200"]
    cookie = login["headers"]["Set-Cookie"]
    assert cookie["schema"]["type"] == "string"
    for attribute in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/", "Max-Age"):
        assert attribute in cookie["description"]

    for path, method in (
        ("/api/v1/sessions/current", "delete"),
        ("/api/v1/me/password", "patch"),
    ):
        response = document["paths"][path][method]["responses"]["204"]
        assert "content" not in response
        header = response["headers"]["Set-Cookie"]
        assert "Max-Age=0" in header["description"]
        assert "SameSite=Strict" in header["description"]
        assert (
            header["schema"]["description"]
            == "Empty value; no session token is returned."
        )


def test_422_contract_covers_actual_boundary_and_domain_validation_responses():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/validate", responses=error_responses(422))
    def validate(value: int):
        raise ValidationDomainError(f"invalid value: {value}")

    client = TestClient(app)
    bodies = [
        client.get("/validate?value=not-an-integer").json(),
        client.get("/validate?value=1").json(),
    ]
    schema = app.openapi()["paths"]["/validate"]["get"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]

    for body in bodies:
        assert any(set(branch["required"]).issubset(body) for branch in schema["oneOf"])
