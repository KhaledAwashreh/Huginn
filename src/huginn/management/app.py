"""Management HTTP boundary defined by ADR-0011."""

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any
from uuid import UUID

from flask import Flask, Response, current_app, g, jsonify, make_response, request
from psycopg import IntegrityError
from pydantic import Field, TypeAdapter, ValidationError
from werkzeug.exceptions import HTTPException

from huginn.management.config import ManagementConfig, load_config
from huginn.management.database import (
    ManagementConnectionFactory,
    PostgresReadiness,
    UnitOfWork,
)
from huginn.management.discovery_strategies import ClientDiscoveryStrategyService
from huginn.management.domain import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ManagementDomainError,
    NotFoundError,
    RateLimitError,
    ValidationDomainError,
)
from huginn.management.http import error_response, json_response, parse_json
from huginn.management.ideal_client_profiles import IdealClientProfileService
from huginn.management.identity import (
    LoginService,
    PasswordChangeService,
    PostgresSessionRepository,
    SessionService,
)
from huginn.management.openapi import build_openapi_document
from huginn.management.ports import ReadinessPort
from huginn.management.primitives import PageLimit, PageOffset, StrictModel
from huginn.management.schemas import (
    IcpCreate,
    IcpPatch,
    IcpRead,
    OfferingCreate,
    OfferingPatch,
    OfferingRead,
    ProfessionalProfilePatch,
    ProfessionalProfileRead,
    StrategyCreate,
    StrategyPatch,
    StrategyRead,
    UserPatch,
    UserRead,
)
from huginn.management.service_offerings import ServiceOfferingService
from huginn.management.throttle import FailedLoginThrottle
from huginn.management.user_profile import UserProfileService

_ERROR_CODES = {
    400: ("malformed_json", "Malformed JSON request"),
    401: ("authentication_error", "Request could not be completed"),
    403: ("authorization_error", "Request could not be completed"),
    404: ("not_found", "Request could not be completed"),
    409: ("conflict", "Request could not be completed"),
    422: ("validation_error", "Request validation failed"),
    429: ("rate_limited", "Request could not be completed"),
}


class LoginRequest(StrictModel):
    username: str = Field(min_length=1)
    password: str


class PasswordChangeRequest(StrictModel):
    current_password: str
    new_password: str


def authenticated[RouteT](route: RouteT) -> RouteT:
    """Resolve the active Account and User from a server-side session."""

    @wraps(route)  # type: ignore[arg-type]
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        principal, session = current_app.extensions["huginn.management.authenticate"]()
        g.principal = principal
        g.management_session = session
        return route(*args, **kwargs)  # type: ignore[operator]

    return wrapped  # type: ignore[return-value]


def _clear_session_cookie(response: Response, config: ManagementConfig) -> None:
    response.delete_cookie(
        config.cookie_name,
        path="/",
        secure=bool(config.cookie_secure),
        httponly=True,
        samesite=config.cookie_samesite,
    )


def _validation_details(error: ValidationError) -> list[dict[str, Any]]:
    """Return useful field locations without echoing user supplied values."""
    return [
        {
            "loc": list(
                item["loc"][:-1] if item["type"] == "extra_forbidden" else item["loc"]
            ),
            "code": item["type"],
            "message": "Invalid value",
        }
        for item in error.errors(
            include_input=False,
            include_context=False,
            include_url=False,
        )
    ]


def _integer_query(name: str, default: str, adapter: TypeAdapter[Any]) -> Any:
    """Parse a non-negative decimal query parameter as a validated integer."""
    raw = request.args.get(name, default)
    if not raw.isascii() or not raw.isdecimal():
        raise ValidationError.from_exception_data(
            "Query", [{"type": "int_parsing", "loc": (name,), "input": raw}]
        )
    try:
        value = int(raw)
    except ValueError as error:
        # CPython rejects decimal strings above its safety digit limit. Keep
        # that input error inside the normal 422 validation response.
        raise ValidationError.from_exception_data(
            "Query", [{"type": "int_parsing", "loc": (name,), "input": raw}]
        ) from error
    return adapter.validate_python(value)


def _domain_status(error: ManagementDomainError) -> int:
    if isinstance(error, AuthenticationError):
        return 401
    if isinstance(error, AuthorizationError):
        return 403
    if isinstance(error, NotFoundError):
        return 404
    if isinstance(error, ConflictError):
        return 409
    if isinstance(error, ValidationDomainError):
        return 422
    if isinstance(error, RateLimitError):
        return 429
    return 500


def create_app(
    config: ManagementConfig | None = None,
    *,
    readiness: ReadinessPort | None = None,
    unit_of_work_factory: Callable[[], Any] | None = None,
    sessions_factory: Callable[[Any], Any] | None = None,
    login_service: Any | None = None,
    password_change_service: Any | None = None,
    user_profile_service: Any | None = None,
    service_offering_service: Any | None = None,
    ideal_client_profile_service: Any | None = None,
    discovery_strategy_service: Any | None = None,
    clock: Callable[[], datetime] | None = None,
    throttle: Any | None = None,
) -> Flask:
    """Create the inert management application defined by ADR-0011."""
    resolved_config = config if config is not None else load_config()
    probe = (
        readiness
        if readiness is not None
        else PostgresReadiness(resolved_config.database_url)
    )
    app = Flask(__name__, static_folder=None)
    app.config["MANAGEMENT_COOKIE_NAME"] = resolved_config.cookie_name
    app.config["MANAGEMENT_COOKIE_SECURE"] = resolved_config.cookie_secure
    app.config["MANAGEMENT_COOKIE_SAMESITE"] = resolved_config.cookie_samesite
    make_uow = unit_of_work_factory or (
        lambda: UnitOfWork(ManagementConnectionFactory(resolved_config.database_url))
    )
    make_sessions = sessions_factory or (
        lambda uow: PostgresSessionRepository(uow.connection)
    )
    login_throttle = throttle or FailedLoginThrottle(
        clock=clock,
        max_failures=resolved_config.login_throttle_failures,
        window=resolved_config.login_throttle_window,
    )
    login = login_service or LoginService(
        make_uow,
        resolved_config,
        login_throttle,
        sessions_factory=make_sessions,
        clock=clock,
    )
    change_password = password_change_service or PasswordChangeService(
        make_uow,
        sessions_factory=make_sessions,
        clock=clock,
    )
    self_service = user_profile_service or UserProfileService(make_uow)
    offerings = service_offering_service or ServiceOfferingService(make_uow)
    icps = ideal_client_profile_service or IdealClientProfileService(make_uow)
    strategies = discovery_strategy_service or ClientDiscoveryStrategyService(make_uow)

    def authenticate_request() -> tuple[Any, Any]:
        token = request.cookies.get(resolved_config.cookie_name)
        if not token:
            raise AuthenticationError("authentication required")
        token_digest = SessionService.digest(token)
        with make_uow() as uow:
            sessions = make_sessions(uow)
            session = sessions.get_by_token_digest(token_digest)
            principal_lookup = getattr(
                sessions, "get_active_principal_by_token_digest", None
            )
            now = clock() if clock is not None else datetime.now(UTC)
            principal = (
                principal_lookup(token_digest, now)
                if principal_lookup is not None
                else None
            )
            if principal is None or session is None:
                raise AuthenticationError("authentication required")
            if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
                csrf = request.headers.get("X-CSRF-Token", "")
                csrf_digest = hashlib.sha256(csrf.encode("utf-8")).hexdigest()
                if not csrf or not hmac.compare_digest(
                    csrf_digest, session.csrf_digest
                ):
                    raise AuthorizationError("valid CSRF proof is required")
            return principal, session

    app.extensions["huginn.management.authenticate"] = authenticate_request

    @app.errorhandler(ManagementDomainError)
    def handle_domain_error(error: ManagementDomainError) -> tuple[Response, int]:
        status = _domain_status(error)
        if status == 500:
            app.logger.error("Unhandled management API exception")
            return error_response(500, "internal_error", "An unexpected error occurred")
        code, message = _ERROR_CODES[status]
        return error_response(status, code, message)

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error: IntegrityError) -> tuple[Response, int]:
        del error
        return error_response(409, "conflict", "Request could not be completed")

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError) -> tuple[Response, int]:
        return error_response(
            422,
            "validation_error",
            "Request validation failed",
            _validation_details(error),
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Response, int]:
        status = error.code or 500
        if status >= 500:
            app.logger.error("Unhandled management API exception")
            return error_response(500, "internal_error", "An unexpected error occurred")
        code, message = _ERROR_CODES.get(
            status,
            (f"http_{status}", "Request could not be completed"),
        )
        return error_response(status, code, message)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> tuple[Response, int]:
        del error
        app.logger.error("Unhandled management API exception")
        return error_response(500, "internal_error", "An unexpected error occurred")

    @app.get("/health")
    def health() -> tuple[Response, int]:
        return jsonify(status="ok"), 200

    @app.get("/ready")
    def ready() -> tuple[Response, int]:
        if probe.is_ready():
            return jsonify(status="ready"), 200
        return jsonify(status="not_ready"), 503

    @app.post("/api/v1/sessions")
    def create_session() -> tuple[Response, int]:
        body = parse_json(LoginRequest)
        issued = login.login(
            username=body.username,
            password=body.password,
            client_ip=request.remote_addr or "",
        )
        response, status = json_response(
            {"csrf_token": issued.csrf_token, "expires_at": issued.expires_at}, 200
        )
        response.set_cookie(
            resolved_config.cookie_name,
            issued.session_token,
            max_age=max(0, int(resolved_config.session_ttl.total_seconds())),
            path="/",
            secure=bool(resolved_config.cookie_secure),
            httponly=True,
            samesite=resolved_config.cookie_samesite,
        )
        return response, status

    @app.delete("/api/v1/sessions/current")
    @authenticated
    def delete_current_session() -> tuple[Response, int]:
        with make_uow() as uow:
            sessions = make_sessions(uow)
            revoked_at = clock() if clock is not None else datetime.now(UTC)
            sessions.revoke_current(g.management_session.id, revoked_at)
            uow.commit()
        response = make_response("", 204)
        _clear_session_cookie(response, resolved_config)
        return response, 204

    @app.patch("/api/v1/me/password")
    @authenticated
    def patch_current_password() -> tuple[Response, int]:
        body = parse_json(PasswordChangeRequest)
        change_password.change_password(
            g.principal.account_id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
        response = make_response("", 204)
        _clear_session_cookie(response, resolved_config)
        return response, 204

    @app.get("/api/v1/me")
    @authenticated
    def get_current_user() -> tuple[Response, int]:
        return json_response(self_service.get_user(g.principal), 200)

    @app.patch("/api/v1/me")
    @authenticated
    def patch_current_user() -> tuple[Response, int]:
        body = parse_json(UserPatch)
        return json_response(self_service.update_user(g.principal, body), 200)

    @app.get("/api/v1/me/professional-profile")
    @authenticated
    def get_current_professional_profile() -> tuple[Response, int]:
        return json_response(self_service.get_profile(g.principal), 200)

    @app.patch("/api/v1/me/professional-profile")
    @authenticated
    def patch_current_professional_profile() -> tuple[Response, int]:
        body = parse_json(ProfessionalProfilePatch)
        return json_response(self_service.update_profile(g.principal, body), 200)

    @app.post("/api/v1/offerings")
    @authenticated
    def create_offering() -> tuple[Response, int]:
        body = parse_json(OfferingCreate)
        return json_response(offerings.create(g.principal, body), 201)

    @app.get("/api/v1/offerings")
    @authenticated
    def list_offerings() -> tuple[Response, int]:
        limit = _integer_query("limit", "50", TypeAdapter(PageLimit))
        offset = _integer_query("offset", "0", TypeAdapter(PageOffset))
        return json_response(
            offerings.list(g.principal, limit=limit, offset=offset), 200
        )

    @app.get("/api/v1/offerings/<uuid:offering_id>")
    @authenticated
    def get_offering(offering_id: UUID) -> tuple[Response, int]:
        return json_response(offerings.get(g.principal, offering_id), 200)

    @app.patch("/api/v1/offerings/<uuid:offering_id>")
    @authenticated
    def patch_offering(offering_id: UUID) -> tuple[Response, int]:
        body = parse_json(OfferingPatch)
        return json_response(offerings.update(g.principal, offering_id, body), 200)

    @app.delete("/api/v1/offerings/<uuid:offering_id>")
    @authenticated
    def delete_offering(offering_id: UUID) -> tuple[Response, int]:
        offerings.delete(g.principal, offering_id)
        return make_response("", 204), 204

    @app.post("/api/v1/ideal-client-profiles")
    @authenticated
    def create_icp() -> tuple[Response, int]:
        body = parse_json(IcpCreate)
        return json_response(icps.create(g.principal, body), 201)

    @app.get("/api/v1/ideal-client-profiles")
    @authenticated
    def list_icps() -> tuple[Response, int]:
        limit = _integer_query("limit", "50", TypeAdapter(PageLimit))
        offset = _integer_query("offset", "0", TypeAdapter(PageOffset))
        return json_response(icps.list(g.principal, limit=limit, offset=offset), 200)

    @app.get("/api/v1/ideal-client-profiles/<uuid:profile_id>")
    @authenticated
    def get_icp(profile_id: UUID) -> tuple[Response, int]:
        return json_response(icps.get(g.principal, profile_id), 200)

    @app.patch("/api/v1/ideal-client-profiles/<uuid:profile_id>")
    @authenticated
    def patch_icp(profile_id: UUID) -> tuple[Response, int]:
        return json_response(
            icps.update(g.principal, profile_id, parse_json(IcpPatch)), 200
        )

    @app.delete("/api/v1/ideal-client-profiles/<uuid:profile_id>")
    @authenticated
    def delete_icp(profile_id: UUID) -> tuple[Response, int]:
        icps.delete(g.principal, profile_id)
        return make_response("", 204), 204

    @app.post("/api/v1/discovery-strategies")
    @authenticated
    def create_strategy() -> tuple[Response, int]:
        return json_response(
            strategies.create(g.principal, parse_json(StrategyCreate)), 201
        )

    @app.get("/api/v1/discovery-strategies")
    @authenticated
    def list_strategies() -> tuple[Response, int]:
        raw_active = request.args.get("active")
        if raw_active is None:
            active = None
        elif raw_active in {"true", "false"}:
            active = raw_active == "true"
        else:
            raise ValidationError.from_exception_data(
                "Query",
                [{"type": "bool_parsing", "loc": ("active",), "input": raw_active}],
            )
        return json_response(
            strategies.list(
                g.principal,
                limit=_integer_query("limit", "50", TypeAdapter(PageLimit)),
                offset=_integer_query("offset", "0", TypeAdapter(PageOffset)),
                active=active,
            ),
            200,
        )

    @app.get("/api/v1/discovery-strategies/<uuid:strategy_id>")
    @authenticated
    def get_strategy(strategy_id: UUID) -> tuple[Response, int]:
        return json_response(strategies.get(g.principal, strategy_id), 200)

    @app.patch("/api/v1/discovery-strategies/<uuid:strategy_id>")
    @authenticated
    def patch_strategy(strategy_id: UUID) -> tuple[Response, int]:
        return json_response(
            strategies.update(g.principal, strategy_id, parse_json(StrategyPatch)), 200
        )

    @app.delete("/api/v1/discovery-strategies/<uuid:strategy_id>")
    @authenticated
    def delete_strategy(strategy_id: UUID) -> tuple[Response, int]:
        strategies.delete(g.principal, strategy_id)
        return make_response("", 204), 204

    @app.get("/openapi.json")
    def openapi_document() -> tuple[Response, int]:
        request_models = {
            ("/api/v1/sessions", "POST"): LoginRequest,
            ("/api/v1/me/password", "PATCH"): PasswordChangeRequest,
            ("/api/v1/me", "PATCH"): UserPatch,
            ("/api/v1/me/professional-profile", "PATCH"): ProfessionalProfilePatch,
            ("/api/v1/offerings", "POST"): OfferingCreate,
            ("/api/v1/offerings/<uuid:offering_id>", "PATCH"): OfferingPatch,
            ("/api/v1/ideal-client-profiles", "POST"): IcpCreate,
            ("/api/v1/ideal-client-profiles/<uuid:profile_id>", "PATCH"): IcpPatch,
            ("/api/v1/discovery-strategies", "POST"): StrategyCreate,
            (
                "/api/v1/discovery-strategies/<uuid:strategy_id>",
                "PATCH",
            ): StrategyPatch,
        }
        models = {
            model.__name__: model
            for model in (
                LoginRequest,
                PasswordChangeRequest,
                UserPatch,
                UserRead,
                ProfessionalProfilePatch,
                ProfessionalProfileRead,
                OfferingCreate,
                OfferingPatch,
                OfferingRead,
                IcpCreate,
                IcpPatch,
                IcpRead,
                StrategyCreate,
                StrategyPatch,
                StrategyRead,
            )
        }

        def model_ref(name: str) -> dict[str, Any]:
            return {"$ref": f"#/components/schemas/{name}"}

        def page_schema(name: str) -> dict[str, Any]:
            return {
                "type": "object",
                "required": ["items", "offset", "limit", "has_more"],
                "properties": {
                    "items": {"type": "array", "items": model_ref(name)},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            }

        response_schemas = {
            ("/health", "GET"): {
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"const": "ok"}},
            },
            ("/ready", "GET"): {
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"const": "ready"}},
            },
            ("/api/v1/sessions", "POST"): {
                "type": "object",
                "required": ["csrf_token", "expires_at"],
                "properties": {
                    "csrf_token": {"type": "string"},
                    "expires_at": {"type": "string", "format": "date-time"},
                },
            },
            ("/api/v1/me", "GET"): model_ref("UserRead"),
            ("/api/v1/me", "PATCH"): model_ref("UserRead"),
            ("/api/v1/me/professional-profile", "GET"): model_ref(
                "ProfessionalProfileRead"
            ),
            ("/api/v1/me/professional-profile", "PATCH"): model_ref(
                "ProfessionalProfileRead"
            ),
            ("/api/v1/offerings", "POST"): model_ref("OfferingRead"),
            ("/api/v1/offerings", "GET"): page_schema("OfferingRead"),
            ("/api/v1/offerings/<uuid:offering_id>", "GET"): model_ref("OfferingRead"),
            ("/api/v1/offerings/<uuid:offering_id>", "PATCH"): model_ref(
                "OfferingRead"
            ),
            ("/api/v1/ideal-client-profiles", "POST"): model_ref("IcpRead"),
            ("/api/v1/ideal-client-profiles", "GET"): page_schema("IcpRead"),
            ("/api/v1/ideal-client-profiles/<uuid:profile_id>", "GET"): model_ref(
                "IcpRead"
            ),
            ("/api/v1/ideal-client-profiles/<uuid:profile_id>", "PATCH"): model_ref(
                "IcpRead"
            ),
            ("/api/v1/discovery-strategies", "POST"): model_ref("StrategyRead"),
            ("/api/v1/discovery-strategies", "GET"): page_schema("StrategyRead"),
            ("/api/v1/discovery-strategies/<uuid:strategy_id>", "GET"): model_ref(
                "StrategyRead"
            ),
            ("/api/v1/discovery-strategies/<uuid:strategy_id>", "PATCH"): model_ref(
                "StrategyRead"
            ),
        }
        # This document is generated from trusted models and intentionally
        # names credential fields; the normal response secret-key guard is for
        # runtime data, not schema metadata.
        return jsonify(
            build_openapi_document(app, request_models, models, response_schemas)
        ), 200

    return app
