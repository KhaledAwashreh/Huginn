"""Composition root for the synchronous management API."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import FastAPI

from huginn.management.config import ManagementConfig, load_config
from huginn.management.database import (
    ManagementConnectionFactory,
    PostgresReadiness,
    UnitOfWork,
)
from huginn.management.errors.handlers import (
    register_exception_handlers,
    suppress_handled_server_error_tracebacks,
)
from huginn.management.openapi_customization import customize_openapi
from huginn.management.repositories.postgres.account import PostgresAccountRepository
from huginn.management.repositories.postgres.discovery_strategy import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.repositories.postgres.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.repositories.postgres.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.repositories.postgres.service_offering import (
    PostgresServiceOfferingRepository,
)
from huginn.management.repositories.postgres.session import PostgresSessionRepository
from huginn.management.repositories.postgres.user import PostgresUserRepository
from huginn.management.routers.current_user import router as current_user_router
from huginn.management.routers.discovery_strategies import (
    router as discovery_strategies_router,
)
from huginn.management.routers.health import router as health_router
from huginn.management.routers.ideal_client_profiles import (
    router as ideal_client_profiles_router,
)
from huginn.management.routers.service_offerings import (
    router as service_offerings_router,
)
from huginn.management.routers.sessions import router as sessions_router
from huginn.management.services.authentication import AuthenticationService
from huginn.management.services.discovery_strategies import (
    ClientDiscoveryStrategyService,
)
from huginn.management.services.ideal_client_profiles import IdealClientProfileService
from huginn.management.services.service_offerings import ServiceOfferingService
from huginn.management.services.user_profile import UserProfileService
from huginn.management.throttle import FailedLoginThrottle


@dataclass(frozen=True, slots=True)
class ManagementDependencies:
    """Immutable references to application services and infrastructure."""

    config: ManagementConfig
    readiness: Any
    unit_of_work_factory: Callable[[], Any]
    sessions_factory: Callable[[Any], Any]
    login_service: Any
    authentication_service: Any
    password_change_service: Any
    user_profile_service: Any
    service_offering_service: Any
    ideal_client_profile_service: Any
    discovery_strategy_service: Any
    clock: Callable[[], datetime] | None = None


def create_app(
    config: ManagementConfig | None = None,
    *,
    readiness: Any | None = None,
    unit_of_work_factory: Callable[[], Any] | None = None,
    sessions_factory: Callable[[Any], Any] | None = None,
    login_service: Any | None = None,
    authentication_service: Any | None = None,
    password_change_service: Any | None = None,
    user_profile_service: Any | None = None,
    service_offering_service: Any | None = None,
    ideal_client_profile_service: Any | None = None,
    discovery_strategy_service: Any | None = None,
    clock: Callable[[], datetime] | None = None,
    throttle: Any | None = None,
) -> FastAPI:
    """Build the app and its dependency graph without opening a connection."""
    resolved_config = config if config is not None else load_config()
    probe = (
        readiness
        if readiness is not None
        else PostgresReadiness(resolved_config.database_url)
    )
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
    auth = (
        authentication_service
        if authentication_service is not None
        else AuthenticationService(
            make_uow,
            resolved_config,
            login_throttle,
            accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
            sessions_factory=make_sessions,
            clock=clock,
        )
    )
    login = login_service if login_service is not None else auth
    change_password = (
        password_change_service if password_change_service is not None else auth
    )
    dependencies = ManagementDependencies(
        config=resolved_config,
        readiness=probe,
        unit_of_work_factory=make_uow,
        sessions_factory=make_sessions,
        login_service=login,
        authentication_service=auth,
        password_change_service=change_password,
        user_profile_service=user_profile_service
        if user_profile_service is not None
        else UserProfileService(
            make_uow,
            users_factory=lambda uow: PostgresUserRepository(uow.connection),
            profiles_factory=lambda uow: PostgresProfessionalProfileRepository(
                uow.connection
            ),
        ),
        service_offering_service=service_offering_service
        if service_offering_service is not None
        else ServiceOfferingService(
            make_uow,
            offerings_factory=lambda uow: PostgresServiceOfferingRepository(
                uow.connection
            ),
        ),
        ideal_client_profile_service=ideal_client_profile_service
        if ideal_client_profile_service is not None
        else IdealClientProfileService(
            make_uow,
            profiles_factory=lambda uow: PostgresIdealClientProfileRepository(
                uow.connection
            ),
        ),
        discovery_strategy_service=discovery_strategy_service
        if discovery_strategy_service is not None
        else ClientDiscoveryStrategyService(
            make_uow,
            strategies_factory=lambda uow: PostgresClientDiscoveryStrategyRepository(
                uow.connection
            ),
            offerings_factory=lambda uow: PostgresServiceOfferingRepository(
                uow.connection
            ),
            profiles_factory=lambda uow: PostgresIdealClientProfileRepository(
                uow.connection
            ),
        ),
        clock=clock,
    )
    app = FastAPI()
    app.state.management = dependencies
    customize_openapi(app)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(current_user_router)
    app.include_router(service_offerings_router)
    app.include_router(ideal_client_profiles_router)
    app.include_router(discovery_strategies_router)
    suppress_handled_server_error_tracebacks(app)
    return app
