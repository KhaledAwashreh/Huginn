import re

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig


def test_openapi_covers_registered_routes_models_security_and_errors():
    app = create_app(
        ManagementConfig("unused", environment="test"),
        readiness=type("Ready", (), {"is_ready": lambda self: True})(),
    )
    document = app.test_client().get("/openapi.json").json
    assert document["openapi"] == "3.1.0"
    expected = {}
    for rule in app.url_map.iter_rules():
        if rule.rule == "/openapi.json":
            continue
        path = re.sub(r"<uuid:([^>]+)>", r"{\1}", rule.rule)
        expected[path] = expected.get(path, set()) | {
            method.lower() for method in rule.methods - {"HEAD", "OPTIONS"}
        }
    assert set(document["paths"]) == set(expected)
    no_content = {
        ("/api/v1/me/password", "patch"),
        ("/api/v1/sessions/current", "delete"),
        ("/api/v1/offerings/{offering_id}", "delete"),
        ("/api/v1/ideal-client-profiles/{profile_id}", "delete"),
        ("/api/v1/discovery-strategies/{strategy_id}", "delete"),
    }
    created = {
        ("/api/v1/offerings", "post"),
        ("/api/v1/ideal-client-profiles", "post"),
        ("/api/v1/discovery-strategies", "post"),
    }
    read_models = {
        ("/api/v1/me", "get"): "UserRead",
        ("/api/v1/me", "patch"): "UserRead",
        ("/api/v1/me/professional-profile", "get"): "ProfessionalProfileRead",
        ("/api/v1/me/professional-profile", "patch"): "ProfessionalProfileRead",
        ("/api/v1/offerings", "post"): "OfferingRead",
        ("/api/v1/offerings/{offering_id}", "get"): "OfferingRead",
        ("/api/v1/offerings/{offering_id}", "patch"): "OfferingRead",
        ("/api/v1/ideal-client-profiles", "post"): "IcpRead",
        ("/api/v1/ideal-client-profiles/{profile_id}", "get"): "IcpRead",
        ("/api/v1/ideal-client-profiles/{profile_id}", "patch"): "IcpRead",
        ("/api/v1/discovery-strategies", "post"): "StrategyRead",
        ("/api/v1/discovery-strategies/{strategy_id}", "get"): "StrategyRead",
        ("/api/v1/discovery-strategies/{strategy_id}", "patch"): "StrategyRead",
    }
    errors = {
        ("/api/v1/sessions", "post"): {"400", "401", "422", "429"},
        ("/api/v1/sessions/current", "delete"): {"401", "403"},
        ("/api/v1/me/password", "patch"): {"400", "401", "403", "422"},
        ("/api/v1/me", "get"): {"401", "404"},
        ("/api/v1/me", "patch"): {"400", "401", "403", "404", "409", "422"},
        ("/api/v1/me/professional-profile", "get"): {"401", "404"},
        ("/api/v1/me/professional-profile", "patch"): {
            "400",
            "401",
            "403",
            "404",
            "409",
            "422",
        },
        ("/api/v1/offerings", "post"): {"400", "401", "403", "409", "422"},
        ("/api/v1/offerings", "get"): {"401", "422"},
        ("/api/v1/offerings/{offering_id}", "get"): {"401", "404"},
        ("/api/v1/offerings/{offering_id}", "patch"): {
            "400",
            "401",
            "403",
            "404",
            "409",
            "422",
        },
        ("/api/v1/offerings/{offering_id}", "delete"): {"401", "403", "404", "409"},
        ("/api/v1/ideal-client-profiles", "post"): {"400", "401", "403", "409", "422"},
        ("/api/v1/ideal-client-profiles", "get"): {"401", "422"},
        ("/api/v1/ideal-client-profiles/{profile_id}", "get"): {"401", "404"},
        ("/api/v1/ideal-client-profiles/{profile_id}", "patch"): {
            "400",
            "401",
            "403",
            "404",
            "409",
            "422",
        },
        ("/api/v1/ideal-client-profiles/{profile_id}", "delete"): {
            "401",
            "403",
            "404",
            "409",
        },
        ("/api/v1/discovery-strategies", "post"): {
            "400",
            "401",
            "403",
            "404",
            "409",
            "422",
        },
        ("/api/v1/discovery-strategies", "get"): {"401", "422"},
        ("/api/v1/discovery-strategies/{strategy_id}", "get"): {"401", "404"},
        ("/api/v1/discovery-strategies/{strategy_id}", "patch"): {
            "400",
            "401",
            "403",
            "404",
            "409",
            "422",
        },
        ("/api/v1/discovery-strategies/{strategy_id}", "delete"): {"401", "403", "404"},
    }
    for path, methods in expected.items():
        assert set(document["paths"][path]) == methods
        for method in methods:
            operation = document["paths"][path][method]
            if path == "/ready" and method == "get":
                assert operation["responses"]["503"]["content"]["application/json"][
                    "schema"
                ] == {
                    "type": "object",
                    "required": ["status"],
                    "properties": {"status": {"const": "not_ready"}},
                }
            expected_status = (
                "204"
                if (path, method) in no_content
                else ("201" if (path, method) in created else "200")
            )
            expected_errors = errors.get((path, method), set())
            expected_response_keys = {expected_status, "default", *expected_errors}
            if path == "/ready" and method == "get":
                expected_response_keys.add("503")
            assert set(operation["responses"]) == expected_response_keys
            for error_status in expected_errors:
                assert operation["responses"][error_status]["content"][
                    "application/json"
                ]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}
            assert expected_status in operation["responses"]
            assert not (
                set(operation["responses"]) & {"200", "201", "204"} - {expected_status}
            )
            if (path, method) in no_content:
                assert "content" not in operation["responses"]["204"]
            elif (path, method) in read_models:
                schema = operation["responses"][expected_status]["content"][
                    "application/json"
                ]["schema"]
                assert schema == {
                    "$ref": f"#/components/schemas/{read_models[path, method]}"
                }
            elif (
                path
                in {
                    "/api/v1/offerings",
                    "/api/v1/ideal-client-profiles",
                    "/api/v1/discovery-strategies",
                }
                and method == "get"
            ):
                schema = operation["responses"]["200"]["content"]["application/json"][
                    "schema"
                ]
                assert schema["required"] == ["items", "offset", "limit", "has_more"]
                assert schema["properties"]["items"]["items"] == {
                    "$ref": "#/components/schemas/"
                    + {
                        "/api/v1/offerings": "OfferingRead",
                        "/api/v1/ideal-client-profiles": "IcpRead",
                        "/api/v1/discovery-strategies": "StrategyRead",
                    }[path]
                }
            else:
                schema = operation["responses"][expected_status]["content"][
                    "application/json"
                ]["schema"]
                assert schema["type"] == "object"
                if path == "/api/v1/sessions":
                    assert schema["required"] == ["csrf_token", "expires_at"]
                    assert schema["properties"]["csrf_token"] == {"type": "string"}
                    assert schema["properties"]["expires_at"] == {
                        "type": "string",
                        "format": "date-time",
                    }
                    cookie_header = operation["responses"]["200"]["headers"][
                        "Set-Cookie"
                    ]
                    assert cookie_header["schema"]["type"] == "string"
                    assert (
                        "opaque 43-character URL-safe token"
                        in cookie_header["schema"]["description"]
                    )
                    assert "HttpOnly" in cookie_header["description"]
                    assert "SameSite" in cookie_header["description"]
                    assert "Path=/" in cookie_header["description"]
                    assert "Secure" in cookie_header["description"]
                    assert "Max-Age" in cookie_header["description"]
                elif path == "/health":
                    assert schema["required"] == ["status"]
                    assert schema["properties"]["status"] == {"const": "ok"}
                elif path == "/ready":
                    assert schema["required"] == ["status"]
                    assert schema["properties"]["status"] == {"const": "ready"}
            assert "responses" in operation
            assert operation["responses"]["default"]["content"]["application/json"][
                "schema"
            ] == {"$ref": "#/components/schemas/ErrorEnvelope"}
            if path.startswith("/api/") and path != "/api/v1/sessions":
                assert "sessionCookie" in operation["security"][0]
                if method in {"post", "patch", "put", "delete"}:
                    assert "csrfHeader" in operation["security"][0]
    for path in (
        "/api/v1/offerings",
        "/api/v1/ideal-client-profiles",
        "/api/v1/discovery-strategies",
    ):
        parameters = document["paths"][path]["get"]["parameters"]
        assert [parameter["name"] for parameter in parameters] == [
            "limit",
            "offset",
        ] + (["active"] if path == "/api/v1/discovery-strategies" else [])
        assert all(parameter["in"] == "query" for parameter in parameters)
        assert all(parameter["required"] is False for parameter in parameters)
        by_name = {parameter["name"]: parameter["schema"] for parameter in parameters}
        assert by_name["limit"] == {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 50,
        }
        assert by_name["offset"] == {
            "type": "integer",
            "minimum": 0,
            "default": 0,
        }
        if path == "/api/v1/discovery-strategies":
            assert by_name["active"] == {"type": "boolean"}
    request_operations = [
        operation
        for operations in document["paths"].values()
        for operation in operations.values()
        if "requestBody" in operation
    ]
    assert len(request_operations) == 10
    assert all(
        operation["requestBody"]["content"]["application/json"]["schema"][
            "$ref"
        ].startswith("#/components/schemas/")
        for operation in request_operations
    )
    schemas = document["components"]["schemas"]
    assert {
        "UserRead",
        "ProfessionalProfileRead",
        "OfferingRead",
        "IcpRead",
        "StrategyRead",
        "ErrorEnvelope",
    } <= schemas.keys()


def test_openapi_documents_session_cookie_clearing_contract():
    app = create_app(
        ManagementConfig(
            "unused",
            cookie_name="custom_session",
            cookie_secure=True,
            cookie_samesite="Strict",
            environment="test",
        ),
        readiness=type("Ready", (), {"is_ready": lambda self: True})(),
    )
    document = app.test_client().get("/openapi.json").json

    for path, method in (
        ("/api/v1/sessions/current", "delete"),
        ("/api/v1/me/password", "patch"),
    ):
        response = document["paths"][path][method]["responses"]["204"]
        assert response["description"] == "Successful response"
        assert "content" not in response
        header = response["headers"]["Set-Cookie"]
        assert header == {
            "description": (
                "Expires the configured custom_session session cookie by setting its "
                "value to empty, Max-Age=0, and an expiry in the past. Attributes: "
                "Path=/, HttpOnly, Secure, and SameSite=Strict."
            ),
            "schema": {
                "type": "string",
                "description": "Empty value; no session token is returned.",
            },
        }
