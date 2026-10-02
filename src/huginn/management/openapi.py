"""Deterministic OpenAPI assembly for the registered management routes."""

import re
from typing import Any

from flask import Flask
from pydantic import BaseModel

_PARAMETER = re.compile(r"<uuid:([^>]+)>")
_LIST_QUERY_PARAMETERS = {
    "/api/v1/offerings": (
        ("limit", {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}),
        ("offset", {"type": "integer", "minimum": 0, "default": 0}),
    ),
    "/api/v1/ideal-client-profiles": (
        ("limit", {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}),
        ("offset", {"type": "integer", "minimum": 0, "default": 0}),
    ),
    "/api/v1/discovery-strategies": (
        ("limit", {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}),
        ("offset", {"type": "integer", "minimum": 0, "default": 0}),
        ("active", {"type": "boolean"}),
    ),
}
_ERROR_STATUSES = {
    ("/api/v1/sessions", "POST"): (400, 401, 422, 429),
    ("/api/v1/sessions/current", "DELETE"): (401, 403),
    ("/api/v1/me/password", "PATCH"): (400, 401, 403, 422),
    ("/api/v1/me", "GET"): (401, 404),
    ("/api/v1/me", "PATCH"): (400, 401, 403, 404, 409, 422),
    ("/api/v1/me/professional-profile", "GET"): (401, 404),
    ("/api/v1/me/professional-profile", "PATCH"): (
        400,
        401,
        403,
        404,
        409,
        422,
    ),
    ("/api/v1/offerings", "POST"): (400, 401, 403, 409, 422),
    ("/api/v1/offerings", "GET"): (401, 422),
    ("/api/v1/offerings/<uuid:offering_id>", "GET"): (401, 404),
    ("/api/v1/offerings/<uuid:offering_id>", "PATCH"): (
        400,
        401,
        403,
        404,
        409,
        422,
    ),
    ("/api/v1/offerings/<uuid:offering_id>", "DELETE"): (401, 403, 404, 409),
    ("/api/v1/ideal-client-profiles", "POST"): (400, 401, 403, 409, 422),
    ("/api/v1/ideal-client-profiles", "GET"): (401, 422),
    ("/api/v1/ideal-client-profiles/<uuid:profile_id>", "GET"): (401, 404),
    ("/api/v1/ideal-client-profiles/<uuid:profile_id>", "PATCH"): (
        400,
        401,
        403,
        404,
        409,
        422,
    ),
    ("/api/v1/ideal-client-profiles/<uuid:profile_id>", "DELETE"): (401, 403, 404, 409),
    ("/api/v1/discovery-strategies", "POST"): (400, 401, 403, 404, 409, 422),
    ("/api/v1/discovery-strategies", "GET"): (401, 422),
    ("/api/v1/discovery-strategies/<uuid:strategy_id>", "GET"): (401, 404),
    ("/api/v1/discovery-strategies/<uuid:strategy_id>", "PATCH"): (
        400,
        401,
        403,
        404,
        409,
        422,
    ),
    ("/api/v1/discovery-strategies/<uuid:strategy_id>", "DELETE"): (401, 403, 404),
}


def _schema_components(models: dict[str, type[BaseModel]]) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for name, model in sorted(models.items()):
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        components.update(schema.pop("$defs", {}))
        components[name] = schema
    return components


def _session_cookie_header(app: Flask, *, clearing: bool) -> dict[str, Any]:
    cookie_name = app.config["MANAGEMENT_COOKIE_NAME"]
    secure = "Secure" if app.config["MANAGEMENT_COOKIE_SECURE"] else "no Secure"
    samesite = app.config["MANAGEMENT_COOKIE_SAMESITE"]
    if clearing:
        description = (
            f"Expires the configured {cookie_name} session cookie by setting its "
            "value to empty, Max-Age=0, and an expiry in the past. Attributes: "
            f"Path=/, HttpOnly, {secure}, and SameSite={samesite}."
        )
        value_description = "Empty value; no session token is returned."
    else:
        description = (
            f"Sets the configured {cookie_name} session cookie. Attributes: "
            "Path=/, HttpOnly, Max-Age equal to the session TTL, "
            f"{secure}, and SameSite={samesite}."
        )
        value_description = (
            "The cookie value is an opaque 43-character URL-safe token and is not "
            "included in the JSON body."
        )
    return {
        "description": description,
        "schema": {"type": "string", "description": value_description},
    }


def build_openapi_document(
    app: Flask,
    request_models: dict[tuple[str, str], type[BaseModel]],
    models: dict[str, type[BaseModel]],
    response_schemas: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
        if rule.rule == "/openapi.json":
            continue
        path = _PARAMETER.sub(r"{\1}", rule.rule)
        parameters = [
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            }
            for name in _PARAMETER.findall(rule.rule)
        ]
        operations: dict[str, Any] = paths.setdefault(path, {})
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            status = (
                "204"
                if (rule.rule, method)
                in {
                    ("/api/v1/sessions/current", "DELETE"),
                    ("/api/v1/me/password", "PATCH"),
                    ("/api/v1/offerings/<uuid:offering_id>", "DELETE"),
                    ("/api/v1/ideal-client-profiles/<uuid:profile_id>", "DELETE"),
                    ("/api/v1/discovery-strategies/<uuid:strategy_id>", "DELETE"),
                }
                else "201"
                if method == "POST" and rule.rule != "/api/v1/sessions"
                else "200"
            )
            response_schema = response_schemas.get((rule.rule, method))
            if status != "204" and response_schema is None:
                raise ValueError(
                    f"Missing OpenAPI response schema for {rule.rule} {method}"
                )
            operation: dict[str, Any] = {
                "operationId": f"{rule.endpoint}_{method.lower()}",
                "responses": {
                    status: {
                        "description": "Successful response",
                        **(
                            {}
                            if status == "204"
                            else {
                                "content": {
                                    "application/json": {"schema": response_schema}
                                }
                            }
                        ),
                    },
                    "default": {
                        "description": "Error response",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                            }
                        },
                    },
                },
            }
            for error_status in _ERROR_STATUSES.get((rule.rule, method), ()):
                operation["responses"][str(error_status)] = {
                    "description": "Error response",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                        }
                    },
                }
            if rule.rule == "/api/v1/sessions" and method == "POST":
                operation["responses"][status]["headers"] = {
                    "Set-Cookie": _session_cookie_header(app, clearing=False)
                }
            if (rule.rule, method) in {
                ("/api/v1/sessions/current", "DELETE"),
                ("/api/v1/me/password", "PATCH"),
            }:
                operation["responses"][status]["headers"] = {
                    "Set-Cookie": _session_cookie_header(app, clearing=True)
                }
            if rule.rule == "/ready" and method == "GET":
                operation["responses"]["503"] = {
                    "description": "Management service is not ready",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["status"],
                                "properties": {"status": {"const": "not_ready"}},
                            }
                        }
                    },
                }
            if parameters:
                operation["parameters"] = parameters
            if method == "GET" and rule.rule in _LIST_QUERY_PARAMETERS:
                operation.setdefault("parameters", []).extend(
                    {
                        "name": name,
                        "in": "query",
                        "required": False,
                        "schema": schema,
                    }
                    for name, schema in _LIST_QUERY_PARAMETERS[rule.rule]
                )
            model = request_models.get((rule.rule, method))
            if model is not None:
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{model.__name__}"}
                        }
                    },
                }
            if rule.rule.startswith("/api/") and rule.rule != "/api/v1/sessions":
                security = {"sessionCookie": []}
                if method in {"POST", "PATCH", "PUT", "DELETE"}:
                    security["csrfHeader"] = []
                operation["security"] = [security]
            operations[method.lower()] = operation
    return {
        "openapi": "3.1.0",
        "info": {"title": "Huginn Management API", "version": "1.0.0"},
        "paths": paths,
        "components": {
            "securitySchemes": {
                "sessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": app.config["MANAGEMENT_COOKIE_NAME"],
                },
                "csrfHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-CSRF-Token",
                },
            },
            "schemas": {
                **_schema_components(models),
                "ErrorEnvelope": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {
                            "type": "object",
                            "required": ["code", "message", "details"],
                            "properties": {
                                "code": {"type": "string"},
                                "message": {"type": "string"},
                                "details": {"type": "array", "items": {}},
                            },
                        }
                    },
                },
            },
        },
    }
