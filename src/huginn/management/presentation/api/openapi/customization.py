"""Small additions to FastAPI's generated management OpenAPI document."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def customize_openapi(app: FastAPI) -> None:
    """Document cookie attributes and the CSRF security scheme FastAPI cannot infer."""

    def generate() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        document = get_openapi(
            title="Huginn Management API",
            version="1.0.0",
            routes=app.routes,
        )
        config = app.state.management.config
        security_schemes = document.setdefault("components", {}).setdefault(
            "securitySchemes", {}
        )
        cookie_scheme = security_schemes.get("SessionCookie")
        if cookie_scheme is not None:
            cookie_scheme["name"] = config.cookie_name
            cookie_scheme["description"] = (
                "Opaque session token transported in an HttpOnly cookie. "
                "The server stores only its digest."
            )
        security_schemes["csrfHeader"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-CSRF-Token",
            "description": "Session-bound proof returned once by login.",
        }
        for path, operations in document["paths"].items():
            for method, operation in operations.items():
                if path.startswith("/api/") and path not in {
                    "/api/v1/sessions",
                    "/api/v1/accounts",
                    "/api/v1/email-verifications",
                    "/api/v1/email-verifications/resend",
                    "/api/v1/password-resets",
                    "/api/v1/password-resets/complete",
                }:
                    requirements = operation.setdefault("security", [])
                    if method in {"post", "patch", "put", "delete"}:
                        requirement = next(
                            (item for item in requirements if "SessionCookie" in item),
                            {"SessionCookie": []},
                        )
                        requirement["csrfHeader"] = []
                        if requirement not in requirements:
                            requirements.append(requirement)
                if (path, method) == ("/api/v1/sessions", "post"):
                    _set_cookie_header(
                        operation["responses"]["200"], config, clearing=False
                    )
                elif (path, method) in {
                    ("/api/v1/sessions/current", "delete"),
                    ("/api/v1/me/password", "patch"),
                }:
                    _set_cookie_header(
                        operation["responses"]["204"], config, clearing=True
                    )
        app.openapi_schema = document
        return document

    app.openapi = generate  # type: ignore[method-assign]


def _set_cookie_header(
    response: dict[str, Any], config: Any, *, clearing: bool
) -> None:
    secure = "Secure" if config.cookie_secure else "no Secure"
    if clearing:
        description = (
            f"Expires the configured {config.cookie_name} session cookie by setting "
            "its value to empty, Max-Age=0, and an expiry in the past. Attributes: "
            f"Path=/, HttpOnly, {secure}, and SameSite={config.cookie_samesite}."
        )
        value_description = "Empty value; no session token is returned."
    else:
        description = (
            f"Sets the configured {config.cookie_name} session cookie. Attributes: "
            "Path=/, HttpOnly, Max-Age equal to the session TTL, "
            f"{secure}, and SameSite={config.cookie_samesite}."
        )
        value_description = (
            "Opaque 43-character URL-safe token; it is not included in the JSON body."
        )
    response.setdefault("headers", {})["Set-Cookie"] = {
        "description": description,
        "schema": {"type": "string", "description": value_description},
    }
